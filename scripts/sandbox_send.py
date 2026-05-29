#!/usr/bin/env python
"""Sandbox control-surface sender — drives the REAL ingestion endpoints and
emits a single JSON object on stdout for the UI BFF to relay.

This is NOT a fake send. Every mode performs the same signed network call the
demo CLIs use:

* Tier 1 (``--mode tier1`` / ``--mode pool``): builds an Anexo-1A-shaped
  granular payload and POSTs it to ``/v1/sandbox/complaints/granular`` with the
  full security chain (OAuth client_credentials + HMAC SHA-256 + Idempotency-Key
  + dev XFCC), reusing ``scripts/institution_push_demo.py``.
* Tier 2 (``--mode tier2``): builds a real Anexo-1A CSV + manifest and POSTs the
  multipart upload to ``/v1/batches`` (OAuth scope ``batch:upload`` + multipart
  HMAC over the CSV bytes + Idempotency-Key + XFCC). ``--mode tier2-status`` GETs
  ``/v1/batches/{id}``.

Only the two seeded Tier-1 institutions can push: banco-tier1 (SBS-001234) and
coopac-tier2 (SBS-005678). Data is synthetic; the network call, security chain,
redaction, data-quality, worker, and SSE behaviour on the SBS side are real.

stdout is JSON only (machine-readable for the BFF); diagnostics go to stderr.
Exit code is non-zero only on a usage/setup error, never on an API rejection
(the rejection is reported inside the JSON so the UI can show the real result).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import httpx  # noqa: E402

from institution_push_demo import (  # noqa: E402
    PROFILES,
    Profile,
    _basic_auth_header,
    _build_canonical_request,
    _dev_proxy_headers,
    _fetch_token,
    _make_client,
    _now_rfc3339,
    _post_complaint,
    _sign,
)
from nrt_feed import _build_payload  # noqa: E402

# Anexo-1A CSV column order the Tier-2 worker (csv.DictReader → Complaint) expects.
CSV_HEADER = [
    "complaint_id", "institution_id", "received_date", "complainant_doc_type",
    "product_category", "channel", "motivo_code", "severity", "description_text",
    "description_language", "complainant_age_range", "complainant_district",
    "submission_method", "original_reference_id", "resolution_status",
]
_PRODUCTS = ["DEPOSITOS", "CREDITOS", "TARJETA_CREDITO", "TARJETA_DEBITO", "SEGUROS"]
_CHANNELS = ["AGENCIA", "WEB", "APP_MOVIL", "TELEFONO"]
_MOTIVOS = [
    "COBRO_INDEBIDO", "OPERACION_NO_RECONOCIDA", "DEMORA_ATENCION",
    "INFORMACION_INCORRECTA", "INCUMPLIMIENTO_CONTRATO", "CALIDAD_SERVICIO",
]
_SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
_AGES = ["25_34", "35_44", "45_54", "55_64", "UNDER_25", "OVER_64"]
_DISTRICTS = ["150101", "150102", "150114", "040101", "130101", "070101"]
_DOC_TYPES = ["DNI", "CE", "RUC"]
_SUBMISSION = ["APP_MOVIL", "WEB", "AGENCIA", "CAJERO", "POS"]


def _emit(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def _err(msg: str) -> None:
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def _rng(seed: int | None):
    import random

    return random.Random(seed)


# --------------------------------------------------------------------------
# Tier 1 — granular
# --------------------------------------------------------------------------


def _payload_summary(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "institution_id": p.get("institution_id"),
        "institution_name": p.get("institution_name"),
        "motive": p.get("motive"),
        "product": p.get("product"),
        "channel": p.get("channel_in"),
        "severity": p.get("severity"),
        "narrative": p.get("narrative"),
        "institution_complaint_id": p.get("institution_complaint_id"),
    }


def cmd_pool(args: argparse.Namespace) -> int:
    profile = PROFILES[args.profile]
    rng = _rng(None)
    candidates = []
    for i in range(max(1, args.count)):
        p = _build_payload(rng, profile)
        candidates.append({"idx": i, **_payload_summary(p), "payload": p})
    _emit({
        "profile": profile.name,
        "institution_id": profile.institution_id,
        "institution_name": profile.institution_display,
        "candidates": candidates,
    })
    return 0


def cmd_tier1(args: argparse.Namespace) -> int:
    profile = PROFILES[args.profile]
    client = _make_client(api_base=args.api_base, profile=profile, insecure_skip_mtls=True)
    dev_headers = _dev_proxy_headers(profile=profile, insecure_skip_mtls=True)
    results: list[dict[str, Any]] = []
    try:
        token = _fetch_token(client, api_base=args.api_base, profile=profile, dev_proxy_headers=dev_headers)
        if args.payload_file == "-":
            payloads = [json.loads(sys.stdin.read())]
        elif args.payload_file:
            payloads = [json.loads(Path(args.payload_file).read_text(encoding="utf-8"))]
        else:
            rng = _rng(None)
            payloads = [_build_payload(rng, profile) for _ in range(max(1, args.count))]

        for p in payloads:
            p = dict(p)
            # Refresh per-send identifiers so a re-send of a selected complaint
            # creates a distinct canonical complaint (no idempotency collision).
            p["received_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            p["client_submission_id"] = f"sbx-{secrets.token_hex(4)}"
            try:
                resp, _ts, _sig = _post_complaint(
                    client, api_base=args.api_base, profile=profile, token=token,
                    body_dict=p, idempotency_key=f"sbx-{uuid.uuid4().hex[:24]}",
                    dev_proxy_headers=dev_headers,
                )
                if resp.status_code == 401:  # token expired → refresh once
                    token = _fetch_token(client, api_base=args.api_base, profile=profile, dev_proxy_headers=dev_headers)
                    resp, _ts, _sig = _post_complaint(
                        client, api_base=args.api_base, profile=profile, token=token,
                        body_dict=p, idempotency_key=f"sbx-{uuid.uuid4().hex[:24]}",
                        dev_proxy_headers=dev_headers,
                    )
                try:
                    body = resp.json()
                except json.JSONDecodeError:
                    body = {"raw": resp.text[:400]}
                results.append({
                    "ok": resp.status_code in (200, 201),
                    "http_status": resp.status_code,
                    "complaint_id": (body or {}).get("complaint_id"),
                    "decision": (body or {}).get("decision") or (body or {}).get("status"),
                    "institution_id": profile.institution_id,
                    "institution_name": profile.institution_display,
                    "motive": p.get("motive"),
                    "product": p.get("product"),
                    "channel": p.get("channel_in"),
                    "severity": p.get("severity"),
                    "receipt": body,
                })
            except Exception as exc:  # noqa: BLE001 — keep the batch loop alive
                results.append({"ok": False, "http_status": None, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        client.close()

    _emit({
        "profile": profile.name,
        "institution_id": profile.institution_id,
        "institution_name": profile.institution_display,
        "sent_ok": sum(1 for r in results if r.get("ok")),
        "sent_total": len(results),
        "results": results,
    })
    return 0


# --------------------------------------------------------------------------
# Tier 2 — batch
# --------------------------------------------------------------------------


def _fetch_token_scoped(client: httpx.Client, *, api_base: str, profile: Profile, dev_headers: dict[str, str], scope: str) -> str:
    url = f"{api_base.rstrip('/')}/oauth/token"
    headers = {
        "Authorization": _basic_auth_header(profile.client_id, profile.client_secret),
        "Content-Type": "application/x-www-form-urlencoded",
        **dev_headers,
    }
    resp = client.post(url, data={"grant_type": "client_credentials", "scope": scope}, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"OAuth token (scope={scope}) failed: HTTP {resp.status_code}: {resp.text[:200]}")
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError("no access_token in token response")
    return token


def _build_csv(profile: Profile, n: int, rng) -> tuple[bytes, int]:
    pfx = "BCO" if profile.institution_id == "SBS-001234" else "COP"
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_HEADER)
    seen: set[str] = set()
    today = datetime.now(timezone.utc).date()
    for _ in range(n):
        while True:
            cid = f"{pfx}-2026-{rng.randint(600000, 9999999)}"
            if cid not in seen:
                seen.add(cid)
                break
        product = rng.choice(_PRODUCTS)
        channel = rng.choice(_CHANNELS)
        motivo = rng.choice(_MOTIVOS)
        amount = f"{round(rng.uniform(30, 6000), 2):.2f}"
        desc = (
            f"Reclamo por {motivo.replace('_', ' ').lower()} de S/ {amount} "
            f"en {product.replace('_', ' ').lower()} registrado por {channel.lower()}."
        )
        w.writerow([
            cid, profile.institution_id, (today - timedelta(days=rng.randint(0, 20))).isoformat(),
            rng.choice(_DOC_TYPES), product, channel, motivo, rng.choice(_SEVERITIES),
            desc, "es", rng.choice(_AGES), rng.choice(_DISTRICTS),
            rng.choice(_SUBMISSION), "", "pendiente",
        ])
    data = buf.getvalue().encode("utf-8")
    return data, n


def cmd_tier2(args: argparse.Namespace) -> int:
    profile = PROFILES[args.profile]
    n = max(1, min(args.rows, 500))
    rng = _rng(None)
    csv_bytes, row_count = _build_csv(profile, n, rng)
    checksum = hashlib.sha256(csv_bytes).hexdigest()

    today = datetime.now(timezone.utc).date()
    manifest = {
        "reporting_period_start": (today - timedelta(days=30)).isoformat(),
        "reporting_period_end": today.isoformat(),
        "row_count_submitted": row_count,
        "checksum_sha256": checksum,
    }
    manifest_json = json.dumps(manifest, separators=(",", ":"))

    client = _make_client(api_base=args.api_base, profile=profile, insecure_skip_mtls=True)
    dev_headers = _dev_proxy_headers(profile=profile, insecure_skip_mtls=True)
    try:
        token = _fetch_token_scoped(
            client, api_base=args.api_base, profile=profile,
            dev_headers=dev_headers, scope="batch:upload status:read",
        )
        target = "/v1/batches"
        url = f"{args.api_base.rstrip('/')}/batches"
        import urllib.parse

        host = urllib.parse.urlparse(args.api_base).netloc or "localhost"
        timestamp = _now_rfc3339()
        # Multipart HMAC: body-hash is over the CSV bytes only (ADR 0027 amendment).
        canonical = _build_canonical_request(
            method="POST", target=target, host=host, timestamp=timestamp,
            body=csv_bytes, institution_id=profile.institution_id,
        )
        signature = _sign(profile.hmac_secret_hex, canonical)
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": f"sbx-batch-{uuid.uuid4().hex[:20]}",
            "X-SBS-Timestamp": timestamp,
            "X-SBS-Signature": signature,
            "X-SBS-Institution-Id": profile.institution_id,
            **dev_headers,
        }
        resp = client.post(
            url,
            data={"manifest": manifest_json},
            files={"file": (f"sandbox-{secrets.token_hex(3)}.csv", csv_bytes, "text/csv")},
            headers=headers,
        )
        try:
            body = resp.json()
        except json.JSONDecodeError:
            body = {"raw": resp.text[:400]}
        _emit({
            "ok": resp.status_code in (200, 201, 202),
            "http_status": resp.status_code,
            "batch_id": (body or {}).get("batch_id"),
            "status": (body or {}).get("status"),
            "institution_id": profile.institution_id,
            "institution_name": profile.institution_display,
            "row_count_submitted": row_count,
            "checksum_sha256": checksum,
            "location": resp.headers.get("Location"),
            "receipt": body,
        })
    except Exception as exc:  # noqa: BLE001
        _emit({"ok": False, "http_status": None, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        client.close()
    return 0


def cmd_tier2_status(args: argparse.Namespace) -> int:
    profile = PROFILES[args.profile]
    client = _make_client(api_base=args.api_base, profile=profile, insecure_skip_mtls=True)
    dev_headers = _dev_proxy_headers(profile=profile, insecure_skip_mtls=True)
    try:
        token = _fetch_token_scoped(
            client, api_base=args.api_base, profile=profile,
            dev_headers=dev_headers, scope="batch:upload status:read",
        )
        url = f"{args.api_base.rstrip('/')}/batches/{args.batch_id}"
        resp = client.get(url, headers={"Authorization": f"Bearer {token}", **dev_headers})
        try:
            body = resp.json()
        except json.JSONDecodeError:
            body = {"raw": resp.text[:400]}
        _emit({"ok": resp.status_code == 200, "http_status": resp.status_code, **(body if isinstance(body, dict) else {"receipt": body})})
    except Exception as exc:  # noqa: BLE001
        _emit({"ok": False, "http_status": None, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        client.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    p.add_argument("--mode", required=True, choices=["pool", "tier1", "tier2", "tier2-status"])
    p.add_argument("--api-base", default="http://localhost:8000/v1")
    p.add_argument("--profile", choices=sorted(PROFILES.keys()), default="banco-tier1")
    p.add_argument("--count", type=int, default=1, help="tier1: number to send; pool: candidates to generate.")
    p.add_argument("--rows", type=int, default=20, help="tier2: rows in the generated CSV.")
    p.add_argument("--payload-file", default=None, help="tier1: path to a JSON payload to send instead of generating.")
    p.add_argument("--batch-id", default=None, help="tier2-status: the batch id to poll.")
    args = p.parse_args(argv)

    if args.mode == "pool":
        return cmd_pool(args)
    if args.mode == "tier1":
        return cmd_tier1(args)
    if args.mode == "tier2":
        return cmd_tier2(args)
    if args.mode == "tier2-status":
        if not args.batch_id:
            _err("tier2-status requires --batch-id")
            return 2
        return cmd_tier2_status(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
