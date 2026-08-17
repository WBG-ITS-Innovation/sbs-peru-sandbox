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
6. **Cloud leg (v0.2.0, opt-in).** With real Azure credentials, the legal
   opt-in recorded and an egress capture path set, submits one further
   signed Tier-1 complaint whose narrative carries planted synthetic PII
   (a valid DNI, a valid RUC, a phone and an email), then asserts:
   ``agent_runs.model_provider = 'cloud'`` for every model-served agent; one
   ``cloud_inference_audit`` row per outbound call with
   ``redaction_applied = true`` and no text column on the table; and — the
   assertion that matters — that **none of the planted values appear in the
   payload the provider handed to the transport**, read back from the
   capture file. Skipped with a specific reason, and an explicit note that a
   skip is not evidence, whenever the preconditions are absent.

   Two things this leg deliberately does **not** assert. It does not require
   the egress sweep to have caught anything: redaction is layered, the
   ingestion path anonymises first, so a sweep that finds nothing is the
   system working rather than failing. And it treats the *absence* of
   narrative text in the payload as the property to pin — the agents' tools
   run locally and only their structured output reaches the model, so the
   complainant's words never egress at all. Redaction at the boundary is the
   backstop behind that design, not the only thing holding the line.

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

# How long to wait for a complaint's agent rows to land. 60s is ample for the
# fixture-backed and on-prem providers, and far too short for live cloud
# inference: a single investigation turn against Azure has been measured at 15s
# and a full four-agent chain at ~98s, which used to fail this gate for the
# wrong reason. Scaled by the configured provider, and overridable.
POLL_TIMEOUT_S = int(os.environ.get("SBS_STAGE_H_POLL_TIMEOUT_S", "0")) or (
    240 if os.environ.get("SBS_API_MODEL_PROVIDER", "").strip() == "cloud" else 60
)


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


# --------------------------------------------------------------------------
# Cloud leg (v0.2.0). Runs only when real Azure credentials are present and
# the legal opt-in is recorded; skipped, loudly and specifically, otherwise.
#
# What it proves that no unit test can: that the *running API process*, on the
# canonical signed Tier-1 ingestion path, sends nothing identifying to Azure.
# Synthetic PII is planted in the narrative, the complaint is submitted over
# the full chain, and the exact payload handed to the transport is read back
# from the egress capture file and searched for each planted value.
# --------------------------------------------------------------------------

# Deliberately distinctive values: a valid 8-digit DNI, a valid 11-digit RUC
# and an email on a reserved domain. Each must be detectable by the redaction
# engine and each must be absent from the outbound payload.
PLANTED_DNI = "45678912"
PLANTED_RUC = "20512345678"
PLANTED_EMAIL = "planted.canary@sandbox.example.com"
PLANTED_PHONE = "987 654 321"
PLANTED = {
    "DNI": PLANTED_DNI,
    "RUC": PLANTED_RUC,
    "email": PLANTED_EMAIL,
    "phone": PLANTED_PHONE,
}

CLOUD_ENV_VARS = (
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
)


def _cloud_leg_preconditions() -> str | None:
    """Return a reason to skip the cloud leg, or None to run it."""

    if os.environ.get("SBS_STAGE_H_CLOUD", "").lower() in ("0", "false", "no"):
        return "SBS_STAGE_H_CLOUD is explicitly disabled"

    missing = [v for v in CLOUD_ENV_VARS if not os.environ.get(v, "").strip()]
    if missing:
        return f"no Azure credentials in the environment (missing {', '.join(missing)})"

    if os.environ.get("SBS_API_CLOUD_LEGAL_APPROVED", "").lower() != "true":
        return (
            "SBS_API_CLOUD_LEGAL_APPROVED is not true — the cloud path is "
            "gated on a recorded legal opt-in"
        )

    if not os.environ.get("SBS_API_CLOUD_EGRESS_CAPTURE_PATH", "").strip():
        return (
            "SBS_API_CLOUD_EGRESS_CAPTURE_PATH is not set, so the outbound "
            "payload cannot be captured and the redaction proof cannot be made"
        )

    return None


def _submit_tier1_with_planted_pii(suffix: str) -> str:
    """Signed Tier-1 POST whose narrative carries synthetic PII."""

    complaint_id = f"{TIER1['prefix']}-2026-{suffix}"
    token = _token(TIER1, "complaints:write complaints:read")
    narrative = (
        "stage-h-full cloud leg: el cliente con DNI "
        f"{PLANTED_DNI} y la empresa RUC {PLANTED_RUC} reportan un cobro de "
        "comision no autorizado de S/ 120.00. Contacto: "
        f"+51 {PLANTED_PHONE}, correo {PLANTED_EMAIL}."
    )
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
            "description_text": narrative,
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
        "-H", f"Idempotency-Key: stage-h-cloud-{suffix}",
        "-H", f"X-SBS-Timestamp: {timestamp}",
        "-H", f"X-SBS-Signature: hmac-sha256-v1={sig}",
        "-H", f"X-SBS-Institution-Id: {TIER1['institution_id']}",
        "--data", body,
        f"{BASE}/v1/complaints",
    )
    status = out.strip().splitlines()[-1]
    if status != "201":
        _fail(f"cloud leg: Tier-1 POST returned {status}: {out[:400]}")
    _log(f"cloud leg: 201 Created {complaint_id} (narrative carries planted PII)")
    return complaint_id


async def _assert_cloud_provenance(complaint_id: str) -> None:
    """agent_runs must record provider=cloud for this complaint."""

    conn = await asyncpg.connect(LIVE_DSN)
    try:
        deadline = time.time() + POLL_TIMEOUT_S
        runs: list = []
        while time.time() < deadline:
            runs = await conn.fetch(
                "SELECT agent_name, status, model_provider, "
                "       COALESCE(jsonb_array_length(tool_calls), 0) AS n_tools "
                "FROM agent_runs WHERE complaint_id = $1 ORDER BY started_at",
                complaint_id,
            )
            if any(r["agent_name"] == "triage" for r in runs):
                break
            await asyncio.sleep(1)
        else:
            _fail(
                f"cloud leg: no triage agent_run for {complaint_id} within "
                f"{POLL_TIMEOUT_S}s"
            )

        summary = ", ".join(
            f"{r['agent_name']}(status={r['status']},provider={r['model_provider']},"
            f"tools={r['n_tools']})"
            for r in runs
        )
        _log(f"cloud leg: agent_runs {summary}")

        model_served = [
            r for r in runs if r["agent_name"] in ("triage", "investigation", "synthesis")
        ]
        for run in model_served:
            if run["model_provider"] != "cloud":
                _fail(
                    f"cloud leg: {run['agent_name']} recorded "
                    f"model_provider={run['model_provider']!r}, expected 'cloud' — "
                    "the run was not served by Azure"
                )
        _log(
            f"cloud leg: {len(model_served)} model-served run(s) all recorded "
            "model_provider=cloud"
        )
    finally:
        await conn.close()


async def _assert_cloud_inference_audit(complaint_id: str) -> int:
    """One cloud_inference_audit row per model call, redaction_applied true."""

    conn = await asyncpg.connect(LIVE_DSN)
    try:
        rows = await conn.fetch(
            "SELECT agent_name, model_id, redaction_applied, entity_counts, "
            "       message_count "
            "FROM cloud_inference_audit WHERE complaint_id = $1 "
            "ORDER BY created_at",
            complaint_id,
        )
        if not rows:
            _fail(
                f"cloud leg: no cloud_inference_audit rows for {complaint_id} — "
                "the egress audit did not record the outbound calls"
            )

        for row in rows:
            if not row["redaction_applied"]:
                _fail(
                    f"cloud leg: cloud_inference_audit row for "
                    f"{row['agent_name']} has redaction_applied=false — content "
                    "left the process unredacted"
                )

        # The audit table must never hold text. Assert on the actual column
        # set rather than trusting the model definition.
        cols = {
            r["column_name"]
            for r in await conn.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'cloud_inference_audit'"
            )
        }
        forbidden = {
            c for c in cols if c in ("prompt", "messages", "redacted_text", "narrative", "text")
        }
        if forbidden:
            _fail(
                f"cloud leg: cloud_inference_audit has text column(s) {forbidden} — "
                "this table must never store prompt content"
            )

        total_entities = 0
        for row in rows:
            counts = json.loads(row["entity_counts"]) if isinstance(
                row["entity_counts"], str
            ) else dict(row["entity_counts"])
            total_entities += sum(counts.values())
            _log(
                f"cloud leg: audit row agent={row['agent_name']} "
                f"model={row['model_id']} redaction_applied=True "
                f"messages={row['message_count']} entity_counts={counts}"
            )

        # Deliberately NOT asserted: that total_entities > 0.
        #
        # Redaction is layered. The canonical ingestion path anonymises before
        # the agents ever build a prompt, so by the time a payload reaches the
        # egress sweep the planted PII is usually already gone and the sweep
        # correctly finds nothing. An assertion that the sweep must find
        # something would therefore be an assertion that upstream redaction is
        # *failing* — it would pass loudest when the system was at its worst,
        # and on the first live run it passed only because the sweep matched
        # digit runs inside UUIDs in a tool result.
        #
        # The real proof is _assert_no_planted_pii_egressed(): the planted
        # values are absent from the bytes that went on the wire, whichever
        # layer removed them.
        _log(
            f"cloud leg: {len(rows)} audit row(s), all redaction_applied=true, "
            f"{total_entities} entities caught by the egress sweep itself "
            f"(0 is correct when upstream redaction already cleaned the payload)"
        )
        return len(rows)
    finally:
        await conn.close()


def _assert_no_planted_pii_egressed(complaint_id: str) -> None:
    """The proof that matters: read what actually went on the wire.

    The capture file holds the payload CloudProvider handed to the transport,
    post-redaction. If any planted value appears there, it went to Azure.
    """

    path = Path(os.environ["SBS_API_CLOUD_EGRESS_CAPTURE_PATH"])
    if not path.exists():
        _fail(
            f"cloud leg: egress capture file {path} was never written — the "
            "outbound payload could not be inspected, so the redaction claim "
            "is unproven"
        )

    relevant: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("complaint_id") == complaint_id:
            relevant.append(record)

    if not relevant:
        _fail(
            f"cloud leg: no captured egress payloads for {complaint_id} in "
            f"{path} — nothing to verify"
        )

    blob = json.dumps(relevant, ensure_ascii=False)
    leaked = {label: value for label, value in PLANTED.items() if value in blob}
    if leaked:
        _fail(
            "cloud leg: PLANTED PII FOUND IN THE OUTBOUND PAYLOAD — "
            f"{ {k: v for k, v in leaked.items()} }. These values were sent to "
            "Azure. The egress redaction layer did not hold."
        )

    _log(
        f"cloud leg: inspected {len(relevant)} captured outbound payload(s) "
        f"({len(blob)} bytes); NONE of the planted values "
        f"({', '.join(PLANTED)}) appear"
    )
    # Guard against a vacuous pass: the payloads must at least pertain to this
    # complaint, or the leak check proves nothing. The complaint id is the
    # right anchor — it survives redaction untouched and it is what the agents
    # are asked to analyse.
    #
    # Redaction placeholders are deliberately NOT the anchor: on the first live
    # run the only <DNI_n> tokens present came from the sweep matching digit
    # runs inside UUIDs in a tool result, which would have made this check pass
    # while proving nothing.
    if complaint_id not in blob:
        _fail(
            f"cloud leg: none of the captured payloads mention {complaint_id}, "
            "so they do not pertain to this complaint and the leak check would "
            "pass vacuously. Investigate before trusting this result."
        )
    _log(f"cloud leg: payloads reference {complaint_id} — the check is not vacuous")

    # The stronger property, now pinned rather than assumed: the narrative does
    # not egress *at all*. The agents' tools run locally against the database
    # and only their structured outputs reach the model, so the prompt carries
    # the complaint id, a classification label, a data-quality summary and
    # taxonomy results — never the complainant's words. Redaction at the egress
    # boundary is a backstop behind that design, not the thing standing between
    # the narrative and Azure.
    #
    # If this fails, someone has legitimately put narrative text into a prompt.
    # That is a decision to make deliberately, not to discover: confirm the
    # egress sweep catches every entity kind in it, record the data-residency
    # implication, and then update this assertion.
    narrative_fragment = "cobro de comision no autorizado"
    if narrative_fragment in blob:
        _fail(
            "cloud leg: the complaint narrative is now present in the outbound "
            f"payload (found {narrative_fragment!r}). Until now no narrative "
            "text left the process at all — only the complaint id and "
            "structured tool output. This is a data-residency change that must "
            "be made deliberately; see the comment at this assertion."
        )
    _log(
        "cloud leg: no narrative text in any captured payload — the model "
        "received the complaint id plus structured tool output only"
    )


async def _run_cloud_leg(suffix: str) -> None:
    _log("--- Cloud leg: signed Tier-1 POST with provider=cloud ---")
    capture = Path(os.environ["SBS_API_CLOUD_EGRESS_CAPTURE_PATH"])
    _log(f"cloud leg: egress capture at {capture}")

    complaint_id = _submit_tier1_with_planted_pii(suffix)
    await _assert_cloud_provenance(complaint_id)
    n_audit = await _assert_cloud_inference_audit(complaint_id)
    _assert_no_planted_pii_egressed(complaint_id)
    _log(
        f"cloud leg: PASS — provider=cloud persisted, {n_audit} egress audit "
        "row(s) with redaction_applied=true, and no planted PII on the wire"
    )


async def main() -> int:
    _require_services()
    _require_api()

    base = int(time.time()) % 1000000
    # Five distinct ids: two Tier-1 submissions, two Tier-2 batch rows, and
    # one for the cloud leg.
    sfx = [f"{(base + i) % 1000000:06d}" for i in range(5)]

    _log("--- Tier 1: two signed POST /v1/complaints, same process ---")
    tier1_ids = [_submit_tier1(s) for s in sfx[:2]]
    for n, cid in enumerate(tier1_ids, start=1):
        # Submission 2 is the one that used to come back hollow.
        _log(f"tier1: asserting submission {n}/{len(tier1_ids)} ({cid})")
        await _assert_agent_trace(cid, tier="tier1")

    _log("--- Tier 2: signed POST /v1/batches, 2 rows (worker container) ---")
    # Exactly two rows — sfx[4] belongs to the cloud leg, not to this batch.
    batch_id, batch_ids = _submit_tier2(sfx[2:4])
    await _poll_batch_complete(batch_id, expect_rows=len(batch_ids))
    for n, cid in enumerate(batch_ids, start=1):
        _log(f"tier2: asserting row {n}/{len(batch_ids)} ({cid})")
        await _assert_agent_trace(cid, tier="tier2")

    # Cloud leg — opt-in, and explicit about why when it does not run. A
    # skipped leg must never read as a passed one.
    skip_reason = _cloud_leg_preconditions()
    if skip_reason:
        _log("--- Cloud leg: SKIPPED ---")
        _log(f"cloud leg: SKIPPED — {skip_reason}")
        _log(
            "cloud leg: SKIPPED means the cloud egress path was NOT exercised "
            "in this run. It is not evidence that redaction works."
        )
    else:
        await _run_cloud_leg(sfx[4])

    _log("stage-h-full live assertion: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
