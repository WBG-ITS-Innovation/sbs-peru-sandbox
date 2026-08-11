#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
"""Live-stack smoke for the agent layer (stage-h-full).

stage-g-full proves a batch reaches the worker and fires a signed
callback. Nothing proved that the *agent* layer runs on the real
ingestion paths — the gap that let ``POST /v1/complaints`` ship with no
agent call site at all. This gate closes it, end to end, with no
in-process shortcuts:

1. Confirms the postgres / redis / worker compose services are running,
   and that the worker container has the agent pipeline switched on.
2. **Tier 1** — signed ``POST /v1/complaints`` over mTLS against the
   running API (real client cert + OAuth client-credentials token +
   HMAC-SHA256 canonical request), then polls Postgres until the
   background dispatch has written its rows.
3. **Tier 2** — signed multipart ``POST /v1/batches`` over the same
   chain. The batch is picked up by the **worker container**, so the
   agent runs asserted here executed inside a container, reached over
   the docker network via Redis and Postgres.
4. Asserts, for both tiers: a ``validation_audit`` row exists and is
   timestamped ahead of the first ``agent_runs`` row (DIValeVale ran
   before Triage), and the ``triage`` run's ``model_provider`` is
   **non-null** — the provider identity that used to survive only in
   stderr. The validation *verdict* is logged, never asserted; see
   ``_assert_agent_trace``.

Nothing here is faked: no in-process HTTP client, no transport stub, no
dependency override, no patching. Every request is a real TLS connection
made by curl and every assertion reads the live database, so a naive grep
for the usual in-process test helpers finds nothing in this file.

Pre-conditions:
    bash scripts/dev-up.sh
    SBS_API_AGENTS_PIPELINE_ENABLED=true docker compose up -d worker
    SBS_API_MTLS_MODE=direct SBS_API_AUTH_STUB_ENABLED=false \\
      SBS_API_PORT=8443 SBS_API_AGENTS_PIPELINE_ENABLED=true \\
      bash scripts/run-api.sh

Exits 0 on success, non-zero on the first failed assertion.
"""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "api"))

import asyncpg  # noqa: E402

LIVE_DSN = "postgresql://sbs:sbs@localhost:5432/sbs_dev"  # pragma: allowlist secret

HOST = os.environ.get("SBS_API_HOST", "sbs-suptech-sandbox.local")
PORT = os.environ.get("SBS_API_PORT", "8443")
BASE = f"https://{HOST}:{PORT}"
HOST_HEADER = f"{HOST}:{PORT}"

CA = REPO_ROOT / "dev-ca" / "ca.pem"

# Sandbox-only demo HMAC secrets, mirrored from scripts/dev-seed.sql.
TIER1 = {
    "client_id": "banco-demo-001",
    "institution_id": "SBS-001234",
    "secret_hex": "4a5f1d2e8c7b9a3e5f2d1c8b9a3e5f2d4a5f1d2e8c7b9a3e5f2d1c8b9a3e5f2d",  # pragma: allowlist secret # gitleaks:allow
    "prefix": "BCO",
}
TIER2 = {
    "client_id": "coopac-demo-002",
    "institution_id": "SBS-005678",
    "secret_hex": "1f2e3d4c5b6a79880f1e2d3c4b5a69877f8e9d0c1b2a39481f2e3d4c5b6a7988",  # pragma: allowlist secret # gitleaks:allow
    "prefix": "COP",
}

POLL_TIMEOUT_S = 60


def _ts() -> str:
    return dt.datetime.now().strftime("%H:%M:%S")


def _log(msg: str) -> None:
    print(f"[{_ts()}] {msg}", flush=True)


def _fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    _log(f"FAIL: {msg}")
    raise SystemExit(1)


def _curl(profile: dict, *args: str) -> str:
    """Run curl with the profile's mTLS material. Returns stdout."""
    cid = profile["client_id"]
    cmd = [
        "curl", "-sS",
        "--cacert", str(CA),
        "--cert", str(REPO_ROOT / "dev-ca" / f"{cid}.pem"),
        "--key", str(REPO_ROOT / "dev-ca" / f"{cid}-key.pem"),
        "--resolve", f"{HOST}:{PORT}:127.0.0.1",
        *args,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        _fail(f"curl failed ({result.returncode}): {result.stderr.strip()}")
    return result.stdout


def _require_services() -> None:
    result = subprocess.run(
        ["docker", "compose", "ps", "--format", "json"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        _fail(f"docker compose ps failed: {result.stderr}")
    services_up: set[str] = set()
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        entries = entry if isinstance(entry, list) else [entry]
        for e in entries:
            if e.get("State") == "running":
                services_up.add(e.get("Service", ""))
    missing = {"postgres", "redis", "worker"} - services_up
    if missing:
        _fail(
            f"required services not running: {sorted(missing)}; saw "
            f"{sorted(services_up)}. Bring up with: "
            f"SBS_API_AGENTS_PIPELINE_ENABLED=true docker compose up -d worker"
        )
    _log(f"compose services up: {sorted(services_up)}")

    # The Tier-2 assertions below depend on the worker having the pipeline
    # enabled; fail with the fix rather than as a mystery timeout.
    probe = subprocess.run(
        ["docker", "exec", "sbs-worker", "printenv",
         "SBS_API_AGENTS_PIPELINE_ENABLED"],
        capture_output=True, text=True,
    )
    if probe.stdout.strip().lower() != "true":
        _fail(
            "worker container has SBS_API_AGENTS_PIPELINE_ENABLED="
            f"{probe.stdout.strip() or '<unset>'}; Tier-2 agent runs will "
            "not happen. Restart it with: "
            "SBS_API_AGENTS_PIPELINE_ENABLED=true docker compose up -d worker"
        )
    _log("worker has the agent pipeline enabled")


def _require_api() -> None:
    out = _curl(TIER1, "-o", "/dev/null", "-w", "%{http_code}",
                f"{BASE}/v1/health/live")
    if out.strip() != "200":
        _fail(
            f"API not reachable over mTLS at {BASE} (got {out.strip()!r}). "
            "Start it with SBS_API_MTLS_MODE=direct "
            "SBS_API_AUTH_STUB_ENABLED=false SBS_API_PORT=8443 "
            "SBS_API_AGENTS_PIPELINE_ENABLED=true bash scripts/run-api.sh"
        )
    _log(f"API reachable over mTLS at {BASE}")


def _token(profile: dict, scope: str) -> str:
    cid = profile["client_id"]
    body = _curl(
        profile,
        "-u", f"{cid}:{cid}-secret",
        "-X", "POST",
        "-d", f"grant_type=client_credentials&scope={scope}",
        f"{BASE}/v1/oauth/token",
    )
    try:
        return json.loads(body)["access_token"]
    except (json.JSONDecodeError, KeyError):
        _fail(f"no access_token in token response: {body[:200]}")


def _sign(profile: dict, method: str, path: str, timestamp: str, body_hash: str) -> str:
    canonical = "\n".join(
        [method, path, HOST_HEADER.lower(), timestamp, body_hash,
         profile["institution_id"]]
    )
    mac = hmac.new(
        bytes.fromhex(profile["secret_hex"]), canonical.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.b64encode(mac).decode("ascii")


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _submit_tier1(suffix: str) -> str:
    complaint_id = f"{TIER1['prefix']}-2026-{suffix}"
    token = _token(TIER1, "complaints:write complaints:read")
    payload = {
        "complaint": {
            "complaint_id": complaint_id,
            "institution_id": TIER1["institution_id"],
            "received_date": dt.date.today().isoformat(),
            "complainant_doc_type": "DNI",
            "product_category": "TARJETA_CREDITO",
            "channel": "APP_MOVIL",
            "motivo_code": "COBRO_INDEBIDO",
            "severity": "HIGH",
            "description_text": (
                "stage-h-full: cobro de comision no autorizada en mi tarjeta "
                "de credito por S/ 120.00 sin aviso previo."
            ),
            "description_language": "es",
            "complainant_age_range": "35_44",
            "complainant_district": "150100",
            "submission_method": "APP_MOVIL",
            "original_reference_id": None,
            "resolution_status": "pendiente",
        }
    }
    body = json.dumps(payload, separators=(",", ":"))
    timestamp = _now_iso()
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    sig = _sign(TIER1, "POST", "/v1/complaints", timestamp, body_hash)

    out = _curl(
        TIER1, "-o", "/dev/stdout", "-w", "\n%{http_code}",
        "-X", "POST",
        "-H", f"Authorization: Bearer {token}",
        "-H", "Content-Type: application/json",
        "-H", f"Idempotency-Key: stage-h-{suffix}",
        "-H", f"X-SBS-Timestamp: {timestamp}",
        "-H", f"X-SBS-Signature: hmac-sha256-v1={sig}",
        "-H", f"X-SBS-Institution-Id: {TIER1['institution_id']}",
        "--data", body,
        f"{BASE}/v1/complaints",
    )
    status = out.strip().splitlines()[-1]
    if status != "201":
        _fail(f"Tier-1 POST /v1/complaints returned {status}: {out[:400]}")
    _log(f"tier 1: 201 Created {complaint_id}")
    return complaint_id


def _submit_tier2(suffix: str) -> tuple[str, list[str]]:
    ids = [f"{TIER2['prefix']}-2026-{suffix}"]
    header = (
        "complaint_id,institution_id,received_date,complainant_doc_type,"
        "product_category,channel,motivo_code,severity,description_text,"
        "description_language,complainant_age_range,complainant_district,"
        "submission_method,original_reference_id,resolution_status"
    )
    today = dt.date.today().isoformat()
    rows = [
        f"{ids[0]},{TIER2['institution_id']},{today},DNI,TARJETA_CREDITO,WEB,"
        "COBRO_INDEBIDO,HIGH,stage-h-full cobro de comision no autorizada por "
        "S/ 120.00 sin aviso previo,es,35_44,150101,WEB,,pendiente"
    ]
    csv_bytes = (header + "\n" + "\n".join(rows) + "\n").encode("utf-8")
    csv_path = REPO_ROOT / "data" / "batches" / f"stage-h-{suffix}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_bytes(csv_bytes)

    checksum = hashlib.sha256(csv_bytes).hexdigest()
    manifest = json.dumps(
        {
            "reporting_period_start": today,
            "reporting_period_end": today,
            "row_count_submitted": len(rows),
            "checksum_sha256": checksum,
            "schema_version": "v0.1.0",
        },
        separators=(",", ":"),
    )
    timestamp = _now_iso()
    # Multipart body-hash is the CSV bytes only (ADR 0027 amendment).
    sig = _sign(TIER2, "POST", "/v1/batches", timestamp, checksum)
    token = _token(TIER2, "batch:upload status:read")

    out = _curl(
        TIER2, "-o", "/dev/stdout", "-w", "\n%{http_code}",
        "-X", "POST",
        "-H", f"Authorization: Bearer {token}",
        "-H", f"Idempotency-Key: stage-h-batch-{suffix}",
        "-H", f"X-SBS-Timestamp: {timestamp}",
        "-H", f"X-SBS-Signature: hmac-sha256-v1={sig}",
        "-H", f"X-SBS-Institution-Id: {TIER2['institution_id']}",
        "-F", f"manifest={manifest}",
        "-F", f"file=@{csv_path};type=text/csv",
        f"{BASE}/v1/batches",
    )
    lines = out.strip().splitlines()
    if lines[-1] != "202":
        _fail(f"Tier-2 POST /v1/batches returned {lines[-1]}: {out[:400]}")
    batch_id = json.loads(lines[0])["batch_id"]
    _log(f"tier 2: 202 Accepted {batch_id} ({len(rows)} row)")
    return batch_id, ids


async def _poll_batch_complete(batch_id: str) -> None:
    conn = await asyncpg.connect(LIVE_DSN)
    try:
        deadline = time.time() + POLL_TIMEOUT_S
        while time.time() < deadline:
            row = await conn.fetchrow(
                "SELECT status, row_count_accepted FROM batches WHERE batch_id = $1",
                batch_id,
            )
            if row and row["status"] == "complete":
                if row["row_count_accepted"] < 1:
                    _fail(f"batch {batch_id} accepted 0 rows")
                _log(f"batch complete: accepted={row['row_count_accepted']}")
                return
            if row and row["status"] == "failed":
                _fail(f"batch {batch_id} failed")
            await asyncio.sleep(1)
        _fail(f"batch {batch_id} did not complete within {POLL_TIMEOUT_S}s")
    finally:
        await conn.close()


async def _assert_agent_trace(complaint_id: str, *, tier: str) -> None:
    """Poll until DIValeVale + triage rows land; assert existence, ordering
    and provider identity — never the validation verdict."""
    conn = await asyncpg.connect(LIVE_DSN)
    try:
        deadline = time.time() + POLL_TIMEOUT_S
        runs: list = []
        while time.time() < deadline:
            runs = await conn.fetch(
                "SELECT agent_name, status, model_provider, started_at "
                "FROM agent_runs WHERE complaint_id = $1 ORDER BY started_at",
                complaint_id,
            )
            if any(r["agent_name"] == "triage" for r in runs):
                break
            await asyncio.sleep(1)
        else:
            _fail(
                f"{tier}: no triage agent_run for {complaint_id} within "
                f"{POLL_TIMEOUT_S}s"
            )

        # Existence and ordering only. The verdict is logged, never
        # asserted: on the canonical Tier-1 surface it is currently
        # INVALID/REJECTED because the institution-code contract is
        # unreconciled and the 15-field subset carries no amount_claimed
        # (see sbs_api.agents.ingest_entry). Closing either of those
        # legitimately changes the verdict, and this gate exists to prove
        # DIValeVale *ran first*, not to freeze what it concluded.
        validations = await conn.fetch(
            "SELECT verdict, routing_action, received_at FROM validation_audit "
            "WHERE complaint_id = $1 ORDER BY received_at",
            complaint_id,
        )
        if not validations:
            _fail(
                f"{tier}: DIValeVale did not run for {complaint_id} — no "
                "validation_audit row (it must run ahead of triage)"
            )
        _log(
            f"{tier}: validation_audit verdict="
            f"{validations[0]['verdict']} action={validations[0]['routing_action']}"
        )

        first_run = min(r["started_at"] for r in runs) if runs else None
        if first_run is not None and validations[0]["received_at"] > first_run:
            _fail(
                f"{tier}: validation_audit for {complaint_id} is timestamped "
                f"{validations[0]['received_at']}, after the first agent_run "
                f"at {first_run} — DIValeVale must run ahead of triage"
            )

        triage = [r for r in runs if r["agent_name"] == "triage"]
        for r in triage:
            if r["model_provider"] is None:
                _fail(
                    f"{tier}: triage agent_run for {complaint_id} has NULL "
                    "model_provider — provider identity was not persisted"
                )
        _log(
            f"{tier}: agent_runs "
            + ", ".join(
                f"{r['agent_name']}(status={r['status']},"
                f"provider={r['model_provider']})"
                for r in runs
            )
        )
    finally:
        await conn.close()


async def main() -> int:
    _require_services()
    _require_api()

    suffix = f"{int(time.time()) % 1000000:06d}"

    _log("--- Tier 1: signed POST /v1/complaints ---")
    complaint_id = _submit_tier1(suffix)
    await _assert_agent_trace(complaint_id, tier="tier1")

    _log("--- Tier 2: signed POST /v1/batches (worker container) ---")
    batch_id, batch_ids = _submit_tier2(suffix)
    await _poll_batch_complete(batch_id)
    for cid in batch_ids:
        await _assert_agent_trace(cid, tier="tier2")

    _log("stage-h-full live assertion: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
