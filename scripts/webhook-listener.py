#!/usr/bin/env python
"""Demo webhook listener — Workstream G live-stack verification.

Runs as the `webhook-listener` docker-compose service. Stays alive
across multiple smoke-test stages (the smoke script tails its log
rather than waiting for an exit code).

On bind, writes a ``ready`` file into the shared volume so the smoke
test can poll for it before posting a batch. For each received
callback, verifies the HMAC signature against the outbound secret for
the institution and logs one of:

    PASS delivery_id=<id> institution_id=<iid> event=<event_type>
    FAIL delivery_id=<id> institution_id=<iid> reason=<...>

The verification mirrors the canonical-request shape from
:mod:`sbs_api.webhook.signing` (five lines: method / callback-path /
timestamp / body-hash / institution_id). The institution_id comes
from the JSON payload, not from a header, because the spec frames
the listener as institution-side code that already knows its own id.

Outbound secrets are loaded from env vars named
``LISTENER_OUTBOUND_SECRET_<institution_id_with_dashes_to_underscores>``
matching the dev-seed.sql values. Sandbox-only.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "api"))


def _load_secrets() -> dict[str, bytes]:
    """Return {institution_id → outbound HMAC secret} from env."""

    out: dict[str, bytes] = {}
    prefix = "LISTENER_OUTBOUND_SECRET_"
    for name, value in os.environ.items():
        if not name.startswith(prefix):
            continue
        # SBS_001234 → SBS-001234
        institution_id = name[len(prefix):].replace("_", "-", 1)
        try:
            out[institution_id] = bytes.fromhex(value)
        except ValueError:
            print(
                f"FAIL listener_startup reason=secret_not_hex name={name}",
                flush=True,
            )
            continue
    return out


def _verify(
    *,
    secret: bytes,
    method: str,
    callback_path: str,
    timestamp: str,
    body: bytes,
    institution_id: str,
    presented_b64: str,
) -> bool:
    body_hash = hashlib.sha256(body).hexdigest() if body else (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # pragma: allowlist secret
    )
    canonical = "\n".join(
        (method.upper(), callback_path, timestamp, body_hash, institution_id)
    ).encode("utf-8")
    expected = base64.b64encode(
        hmac.new(secret, canonical, hashlib.sha256).digest()
    ).decode("ascii")
    return hmac.compare_digest(expected, presented_b64)


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, secrets: dict[str, bytes]) -> None:
    try:
        # Minimal HTTP/1.1 parse — read request line + headers until \r\n\r\n,
        # then read Content-Length bytes for the body.
        request_line = await reader.readline()
        if not request_line:
            writer.close()
            return
        try:
            method, target, _version = request_line.decode("iso-8859-1").strip().split(" ", 2)
        except ValueError:
            writer.close()
            return

        headers: dict[str, str] = {}
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            try:
                k, v = line.decode("iso-8859-1").rstrip("\r\n").split(":", 1)
                headers[k.strip().lower()] = v.strip()
            except ValueError:
                continue

        content_length = int(headers.get("content-length", "0") or "0")
        body = await reader.readexactly(content_length) if content_length else b""

        # Verify signature.
        ts = headers.get("x-sbs-timestamp", "")
        sig_header = headers.get("x-sbs-signature", "")
        kid = headers.get("x-sbs-key-id", "")
        if not sig_header.startswith("hmac-sha256-v1="):
            await _respond(writer, 400, b'{"reason":"missing or unsupported signature header"}')
            print(
                "FAIL delivery_id=<unknown> institution_id=<unknown> "
                "reason=signature_header_missing_or_wrong_algo",
                flush=True,
            )
            return
        presented = sig_header[len("hmac-sha256-v1="):]

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            await _respond(writer, 400, b'{"reason":"body not JSON"}')
            print(
                "FAIL delivery_id=<unknown> institution_id=<unknown> "
                "reason=body_not_json",
                flush=True,
            )
            return

        institution_id = payload.get("institution_id", "<unknown>")
        event_type = payload.get("event", "<unknown>")
        delivery_id_hint = payload.get("batch_id", "<unknown>")

        secret = secrets.get(institution_id)
        if secret is None:
            await _respond(writer, 401, b'{"reason":"unknown institution"}')
            print(
                f"FAIL delivery_id={delivery_id_hint} institution_id={institution_id} "
                f"reason=secret_not_configured_in_listener",
                flush=True,
            )
            return

        ok = _verify(
            secret=secret,
            method=method,
            callback_path=target,
            timestamp=ts,
            body=body,
            institution_id=institution_id,
            presented_b64=presented,
        )
        if ok:
            await _respond(writer, 200, b'{"ok":true}')
            print(
                f"PASS delivery_id={delivery_id_hint} institution_id={institution_id} "
                f"event={event_type} kid={kid}",
                flush=True,
            )
        else:
            await _respond(writer, 401, b'{"reason":"signature mismatch"}')
            print(
                f"FAIL delivery_id={delivery_id_hint} institution_id={institution_id} "
                f"reason=signature_mismatch",
                flush=True,
            )
    except Exception as exc:  # noqa: BLE001
        try:
            await _respond(writer, 500, b'{"reason":"listener exception"}')
        except Exception:  # noqa: BLE001
            pass
        print(
            f"FAIL delivery_id=<unknown> institution_id=<unknown> "
            f"reason=listener_exception:{type(exc).__name__}:{exc}",
            flush=True,
        )
    finally:
        try:
            await writer.drain()
        except Exception:  # noqa: BLE001
            pass
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass


async def _respond(writer: asyncio.StreamWriter, status: int, body: bytes) -> None:
    reason = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 500: "Internal Server Error"}.get(status, "OK")
    writer.write(
        f"HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode("ascii")
    )
    writer.write(body)


async def main() -> int:
    port = int(os.environ.get("LISTENER_BIND_PORT", "8080"))
    ready_file = os.environ.get("LISTENER_READY_FILE", "/webhook-state/ready")
    secrets = _load_secrets()
    if not secrets:
        print(
            "FAIL listener_startup reason=no_outbound_secrets_configured",
            flush=True,
        )
        return 2

    server = await asyncio.start_server(
        lambda r, w: handle(r, w, secrets), host="0.0.0.0", port=port
    )

    # Signal ready — write file into the shared volume so the smoke
    # script can poll for it before triggering a callback.
    try:
        ready_path = Path(ready_file)
        ready_path.parent.mkdir(parents=True, exist_ok=True)
        ready_path.write_text(
            f"ready at {time.time():.3f} on port {port}\n", encoding="utf-8"
        )
    except OSError as exc:
        print(
            f"FAIL listener_startup reason=ready_file_write_failed:{exc}",
            flush=True,
        )

    print(
        f"webhook-listener bound port={port} institutions={sorted(secrets.keys())}",
        flush=True,
    )

    async with server:
        await server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
