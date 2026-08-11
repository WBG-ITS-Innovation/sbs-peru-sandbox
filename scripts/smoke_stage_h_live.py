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
2. **Tier 1** — **two** signed ``POST /v1/complaints`` back to back over
   mTLS against the running API (real client cert + OAuth
   client-credentials token + HMAC-SHA256 canonical request), then polls
   Postgres until the background dispatch has written its rows.
3. **Tier 2** — signed multipart ``POST /v1/batches`` with **two rows**
   over the same chain. The batch is picked up by the **worker
   container**, so the agent runs asserted here executed inside a
   container, reached over the docker network via Redis and Postgres.
4. Asserts, for both tiers: a ``validation_audit`` row exists and is
   timestamped ahead of the first ``agent_runs`` row (DIValeVale ran
   before Triage), and the ``triage`` run's ``model_provider`` is
   **non-null** — the provider identity that used to survive only in
   stderr. The validation *verdict* is logged, never asserted; see
   ``_assert_agent_trace``.
5. Asserts every ``triage`` run did real work — ``tool_calls`` is
   **non-empty** — and that when triage routes to investigation the
   downstream stages actually ran.

**Why two submissions per tier.** Model providers hold per-run script
state. When that state was keyed per agent instead of per complaint, the
first complaint a process served got a full agent run and every complaint
after it got a hollow one: zero tool calls, ``other @ 0.55``,
``route_to=info-only``, no downstream stages. One submission per tier
cannot see that class of bug — this gate passed against it. Two
submissions into the same process can, and the worker is the sharpest
test of the pair because it is long-lived by construction.

Nothing here is faked: no in-process HTTP client, no transport stub, no
dependency override, no patching. Every request is a real TLS connection
made by curl and every assertion reads the live database, so a naive grep
for the usual in-process test helpers finds nothing in this file.

Pre-conditions:
    bash scripts/dev-up.sh
    SBS_API_AGENTS_PIPELINE_ENABLED=true docker compose up -d worker
    SBS_API_MTLS_MODE=direct SBS_API_AUTH_STUB_ENABLED=false \\
      SBS_API_PORT=8443 SBS_API_AGENTS_PIPELINE_ENABLED=true \\
      SBS_API_RELOAD=false bash scripts/run-api.sh

``SBS_API_RELOAD=false`` is the default now, and it matters here: this
gate asserts steady-state behaviour across two submissions, and a
uvicorn reload between them restarts the API — resetting exactly the
per-process provider state the two submissions exist to test.

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
            "SBS_API_AGENTS_PIPELINE_ENABLED=true SBS_API_RELOAD=false "
            "bash scripts/run-api.sh"
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


def _submit_tier2(suffixes: list[str]) -> tuple[str, list[str]]:
    # Two rows, not one: the worker container is a long-lived process, so
    # two complaints in a single batch is the cheapest way for this gate to
    # see per-process provider state go stale on the Tier-2 side.
    ids = [f"{TIER2['prefix']}-2026-{s}" for s in suffixes]
    header = (
        "complaint_id,institution_id,received_date,complainant_doc_type,"
        "product_category,channel,motivo_code,severity,description_text,"
        "description_language,complainant_age_range,complainant_district,"
        "submission_method,original_reference_id,resolution_status"
    )
    today = dt.date.today().isoformat()
    rows = [
        f"{cid},{TIER2['institution_id']},{today},DNI,TARJETA_CREDITO,WEB,"
        "COBRO_INDEBIDO,HIGH,stage-h-full cobro de comision no autorizada por "
        "S/ 120.00 sin aviso previo,es,35_44,150101,WEB,,pendiente"
        for cid in ids
    ]
    csv_bytes = (header + "\n" + "\n".join(rows) + "\n").encode("utf-8")
    csv_path = REPO_ROOT / "data" / "batches" / f"stage-h-{suffixes[0]}.csv"
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
        "-H", f"Idempotency-Key: stage-h-batch-{suffixes[0]}",
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


async def _poll_batch_complete(batch_id: str, *, expect_rows: int = 1) -> None:
    conn = await asyncpg.connect(LIVE_DSN)
    try:
        deadline = time.time() + POLL_TIMEOUT_S
        while time.time() < deadline:
            row = await conn.fetchrow(
                "SELECT status, row_count_accepted FROM batches WHERE batch_id = $1",
                batch_id,
            )
            if row and row["status"] == "complete":
                if row["row_count_accepted"] < expect_rows:
                    _fail(
                        f"batch {batch_id} accepted "
                        f"{row['row_count_accepted']} rows, expected "
                        f"{expect_rows}"
                    )
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
                "SELECT agent_name, status, model_provider, started_at, "
                "       COALESCE(jsonb_array_length(tool_calls), 0) AS n_tools, "
                "       final_output->>'route_to' AS route_to "
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
            # Non-empty tool_calls is the assertion that catches a provider
            # whose script cursor has run off the end: the run still says
            # status=success, but it did no work. A provider keyed per
            # agent instead of per complaint produces exactly this for
            # every complaint after the first one a process serves.
            if r["n_tools"] < 1:
                _fail(
                    f"{tier}: triage agent_run for {complaint_id} recorded "
                    f"{r['n_tools']} tool calls — the agent produced no work. "
                    "The model provider's script cursor is most likely "
                    "exhausted; it must be keyed per (agent, complaint)."
                )

        # Whatever triage routed to must actually have happened. This is
        # the second half of the same check: a hollow triage run reports
        # route_to=info-only, so a gate that only looked at triage would
        # see a consistent-looking dead end.
        names = {r["agent_name"] for r in runs}
        routes = {r["route_to"] for r in triage if r["route_to"]}
        if "investigation" in routes:
            missing = {"investigation", "synthesis"} - names
            if missing:
                _fail(
                    f"{tier}: triage routed {complaint_id} to investigation "
                    f"but {sorted(missing)} never ran — saw {sorted(names)}"
                )

        _log(
            f"{tier}: agent_runs "
            + ", ".join(
                f"{r['agent_name']}(status={r['status']},"
                f"provider={r['model_provider']},tools={r['n_tools']})"
                for r in runs
            )
        )
    finally:
        await conn.close()


async def main() -> int:
    _require_services()
    _require_api()

    base = int(time.time()) % 1000000
    # Four distinct ids: two Tier-1 submissions and two Tier-2 batch rows.
    sfx = [f"{(base + i) % 1000000:06d}" for i in range(4)]

    _log("--- Tier 1: two signed POST /v1/complaints, same process ---")
    tier1_ids = [_submit_tier1(s) for s in sfx[:2]]
    for n, cid in enumerate(tier1_ids, start=1):
        # Submission 2 is the one that used to come back hollow.
        _log(f"tier1: asserting submission {n}/{len(tier1_ids)} ({cid})")
        await _assert_agent_trace(cid, tier="tier1")

    _log("--- Tier 2: signed POST /v1/batches, 2 rows (worker container) ---")
    batch_id, batch_ids = _submit_tier2(sfx[2:])
    await _poll_batch_complete(batch_id, expect_rows=len(batch_ids))
    for n, cid in enumerate(batch_ids, start=1):
        _log(f"tier2: asserting row {n}/{len(batch_ids)} ({cid})")
        await _assert_agent_trace(cid, tier="tier2")

    _log("stage-h-full live assertion: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
