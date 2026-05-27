#!/usr/bin/env python
"""Submit one Anexo-1A complaint and return a JSON auth-chain trace.

Used by the demo-journey UI (app/src/app/api/journey/submit/route.ts).
Reads a JSON body from stdin (the granular DemoSubmissionRequest shape),
runs the real auth chain, prints a single JSON line to stdout, exits 0.

Trace fields:
    mtls_cn, mtls_thumbprint            mTLS cert evidence
    oauth_jti, oauth_scope, oauth_exp   OAuth token
    hmac_signature_prefix               First 16 chars of the signature
    idempotency_key                     UUID per submission
    http_status, complaint_id           SBS response
    ok                                  Top-level success flag
    error                               String when ok=false

PII safety: stdin bytes are sent on the wire as-is (the SBS endpoint
expects them and redacts on receipt). The printed trace doesn't echo
PII; only structural metadata.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import sys
import time
import urllib.parse
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from institution_push_demo import (  # noqa: E402
    PROFILES,
    _build_canonical_request,
    _cert_thumbprint_sha256_hex,
    _dev_proxy_headers,
    _fetch_token,
    _make_client,
    _post_complaint,
)


def _decode_jwt_unverified(token: str) -> dict:
    try:
        header_b64, payload_b64, _ = token.split(".", 2)
        payload_b64 += "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--profile", default="banco-tier1",
        choices=sorted(PROFILES.keys()),
    )
    p.add_argument(
        "--api-base", default="http://localhost:8000/v1",
    )
    args = p.parse_args()

    profile = PROFILES[args.profile]
    raw = sys.stdin.read()
    try:
        user_body = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"invalid json on stdin: {exc}"}))
        return 1

    # Construct the DemoSubmissionRequest. The UI sends the granular
    # field set (channel_in, product, motive, narrative, etc.). We
    # backfill the mandatory institution metadata from the profile.
    body = {
        "institution_id": profile.institution_id,
        "institution_name": profile.institution_display,
        "client_submission_id": f"journey-{uuid.uuid4().hex[:12]}",
        "demo_scenario": "complaint-journey-demo",
        **user_body,
    }

    # The DemoSubmissionRequest model caps these at 16 chars.
    for k in ("institution_complaint_id", "tid_cli"):
        if isinstance(body.get(k), str):
            body[k] = body[k][:16]

    client = _make_client(
        api_base=args.api_base, profile=profile, insecure_skip_mtls=True,
    )
    dev_proxy_headers = _dev_proxy_headers(profile=profile, insecure_skip_mtls=True)

    trace: dict = {
        "mtls_cn": profile.institution_display,
        "mtls_thumbprint": (
            _cert_thumbprint_sha256_hex(profile.cert_path)
            if profile.cert_path.exists() else None
        ),
    }

    try:
        t0 = time.monotonic()
        token = _fetch_token(
            client, api_base=args.api_base, profile=profile,
            dev_proxy_headers=dev_proxy_headers,
        )
        trace["oauth_elapsed_ms"] = int((time.monotonic() - t0) * 1000)
        jwt_payload = _decode_jwt_unverified(token)
        trace["oauth_jti"] = jwt_payload.get("jti")
        trace["oauth_scope"] = jwt_payload.get("scope")
        trace["oauth_exp"] = jwt_payload.get("exp")
    except SystemExit as exc:
        print(json.dumps({"ok": False, "error": f"oauth: {exc}", "trace": trace}))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "ok": False, "error": f"oauth: {type(exc).__name__}: {exc}",
            "trace": trace,
        }))
        return 0

    idem_key = f"journey-{uuid.uuid4().hex[:24]}"
    trace["idempotency_key"] = idem_key

    try:
        resp, ts_used, sig_used = _post_complaint(
            client, api_base=args.api_base, profile=profile, token=token,
            body_dict=body, idempotency_key=idem_key,
            dev_proxy_headers=dev_proxy_headers,
        )
        trace["hmac_signature_prefix"] = sig_used.split("=", 1)[-1][:16]
        trace["hmac_timestamp"] = ts_used
        trace["http_status"] = resp.status_code
        try:
            payload = resp.json()
        except ValueError:
            payload = {"_raw_text": resp.text[:1000]}
        trace["complaint_id"] = payload.get("complaint_id") if isinstance(payload, dict) else None
        trace["receipt_status"] = payload.get("status") if isinstance(payload, dict) else None

        ok = resp.status_code in (200, 201) and trace["complaint_id"]
        out = {"ok": bool(ok), "trace": trace, "receipt": payload}
        if not ok:
            out["error"] = (
                f"HTTP {resp.status_code}"
                if not isinstance(payload, dict)
                else payload.get("detail") or payload.get("title") or "submission failed"
            )
        print(json.dumps(out, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({
            "ok": False, "error": f"post: {type(exc).__name__}: {exc}",
            "trace": trace,
        }))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
