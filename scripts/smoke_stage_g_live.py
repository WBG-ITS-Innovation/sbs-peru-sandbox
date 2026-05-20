#!/usr/bin/env python
"""Live-stack smoke for Workstream G (Prompt 8 §7).

Exercises the actual signed-callback path end-to-end:

1. Confirms the `worker` and `webhook-listener` compose services are up.
2. Polls ``webhook-state/ready`` to confirm the listener is bound.
3. Hand-generates a small valid CSV + manifest, INSERTs a batch row
   into the live `sbs_dev` Postgres, places the CSV on disk under
   ``data/batches/``.
4. Enqueues ``process_batch`` onto the live arq Redis pool.
5. Polls the batch row until its status reaches ``complete`` or
   ``failed`` (60s timeout).
6. Tails the listener container's log and asserts a PASS line is
   present referencing the same ``batch_id``.

Exits 0 on success; non-zero on any assertion failure. The bash
smoke runner (``scripts/smoke-test-batch.sh stage-g-full``) wraps
this script.
"""

from __future__ import annotations

import asyncio
import csv
import datetime as dt
import hashlib
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "api"))

import asyncpg  # noqa: E402
from arq.connections import RedisSettings, create_pool  # noqa: E402

LIVE_DSN = "postgresql://sbs:sbs@localhost:5432/sbs_dev"  # pragma: allowlist secret
REDIS_URL = "redis://localhost:6379/0"

WEBHOOK_STATE = REPO_ROOT / "webhook-state" / "ready"
STORAGE_DIR = REPO_ROOT / "data" / "batches"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

INSTITUTION_ID = "SBS-001234"


def _new_batch_id() -> str:
    """Match the route handler's batch-id shape."""

    import secrets
    import uuid_utils

    base = str(uuid_utils.uuid7()).replace("-", "")
    return f"batch_{base[:24]}{secrets.token_hex(2)}"


def _ts() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")


def _log(msg: str) -> None:
    print(f"[{_ts()}] {msg}", flush=True)


def _fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    _log(f"FAIL: {msg}")
    sys.exit(1)


def _build_csv() -> tuple[str, bytes]:
    """Three valid Anexo 1-A rows. Returns (sha256_hex, bytes).

    Uses a wall-clock-derived suffix so re-runs of the smoke test
    don't collide on the complaint_id UNIQUE constraint.
    """

    suffix_base = int(time.time()) % 1_000_000
    rows = [
        {
            "complaint_id": f"BCO-2026-{suffix_base * 10 + i:010d}",
            "institution_id": INSTITUTION_ID,
            "received_date": "2026-05-15",
            "complainant_doc_type": "DNI",
            "product_category": "TARJETA_CREDITO",
            "channel": "APP_MOVIL",
            "motivo_code": "COBRO_INDEBIDO",
            "severity": "HIGH",
            "description_text": (
                "Cargo no autorizado por S/ 245.00 - smoke test "
                f"row {i}."
            ),
            "description_language": "es",
            "complainant_age_range": "35_44",
            "complainant_district": "150100",
            "submission_method": "APP_MOVIL",
            "original_reference_id": "",
            "resolution_status": "pendiente",
        }
        for i in range(1, 4)
    ]
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(
        buf,
        fieldnames=list(rows[0].keys()),
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    payload = buf.getvalue().encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), payload


async def _wait_for_listener_ready(timeout_s: int = 15) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if WEBHOOK_STATE.exists():
            _log(f"listener ready: {WEBHOOK_STATE.read_text().strip()}")
            return
        await asyncio.sleep(1)
    _fail(f"webhook-listener did not write {WEBHOOK_STATE} within {timeout_s}s")


def _check_compose_services_up() -> None:
    result = subprocess.run(
        ["docker", "compose", "ps", "--format", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        _fail(f"docker compose ps failed: {result.stderr}")
    # Compose may print one JSON object per line or a single array; normalise.
    services_up: set[str] = set()
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, list):
            for e in entry:
                if e.get("State") == "running":
                    services_up.add(e.get("Service", ""))
        elif entry.get("State") == "running":
            services_up.add(entry.get("Service", ""))
    required = {"postgres", "redis", "worker", "webhook-listener"}
    missing = required - services_up
    if missing:
        _fail(
            f"required services not running: {sorted(missing)}; "
            f"saw {sorted(services_up)}. Bring up with: "
            f"docker compose up -d worker webhook-listener"
        )
    _log(f"compose services up: {sorted(services_up)}")


async def _insert_batch_row(batch_id: str, sha256_hex: str) -> None:
    conn = await asyncpg.connect(LIVE_DSN)
    try:
        await conn.execute(
            """
            INSERT INTO batches (
                batch_id, institution_id, file_name,
                reporting_period_start, reporting_period_end,
                schema_version, row_count_submitted,
                row_count_accepted, row_count_rejected,
                sha256, status, file_path, submitted_at
            ) VALUES (
                $1, $2, $3,
                $4, $5,
                $6, $7,
                0, 0,
                $8, 'pending', $9, now()
            )
            """,
            batch_id,
            INSTITUTION_ID,
            f"{batch_id}.csv",
            dt.date(2026, 5, 1),
            dt.date(2026, 5, 31),
            "v0.1.0",
            3,
            sha256_hex,
            f"{batch_id}.csv",
        )
    finally:
        await conn.close()


async def _poll_batch_until_terminal(batch_id: str, timeout_s: int = 60) -> dict:
    deadline = time.time() + timeout_s
    last_status: str | None = None
    while time.time() < deadline:
        conn = await asyncpg.connect(LIVE_DSN)
        try:
            row = await conn.fetchrow(
                "SELECT batch_id, status, row_count_accepted, "
                "row_count_rejected, failure_reason "
                "FROM batches WHERE batch_id = $1",
                batch_id,
            )
        finally:
            await conn.close()
        if row is None:
            _fail(f"batch {batch_id} not found in DB")
        status = row["status"]
        if status != last_status:
            _log(f"batch.status={status}")
            last_status = status
        if status in {"complete", "failed"}:
            return dict(row)
        await asyncio.sleep(1)
    _fail(
        f"batch {batch_id} did not reach a terminal state within "
        f"{timeout_s}s (last status={last_status})"
    )


def _tail_listener_for_pass(batch_id: str, timeout_s: int = 30) -> None:
    deadline = time.time() + timeout_s
    expected = f"PASS delivery_id={batch_id}"
    while time.time() < deadline:
        result = subprocess.run(
            ["docker", "compose", "logs", "--tail", "200", "webhook-listener"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if expected in result.stdout:
            _log(
                f"listener PASS line present for batch {batch_id}"
            )
            return
        time.sleep(2)
    _fail(
        f"did not see {expected!r} in webhook-listener logs within "
        f"{timeout_s}s of batch completion"
    )


async def _enqueue_process_batch(batch_id: str) -> None:
    pool = await create_pool(
        RedisSettings(host="localhost", port=6379, database=0)
    )
    try:
        job = await pool.enqueue_job("process_batch", batch_id)
        _log(
            f"enqueued process_batch({batch_id}) as job {job.job_id if job else '<none>'}"
        )
    finally:
        await pool.aclose()


async def main() -> int:
    _check_compose_services_up()
    await _wait_for_listener_ready()

    batch_id = _new_batch_id()
    _log(f"using batch_id={batch_id}")

    sha256_hex, payload = _build_csv()
    csv_path = STORAGE_DIR / f"{batch_id}.csv"
    csv_path.write_bytes(payload)
    _log(f"wrote {csv_path} ({len(payload)} bytes, sha256={sha256_hex[:16]}…)")

    await _insert_batch_row(batch_id, sha256_hex)
    _log("inserted batches row in state=pending")

    await _enqueue_process_batch(batch_id)

    row = await _poll_batch_until_terminal(batch_id)
    if row["status"] != "complete":
        _fail(
            f"batch terminal state was {row['status']!r}, "
            f"failure_reason={row['failure_reason']!r}"
        )
    if row["row_count_accepted"] != 3 or row["row_count_rejected"] != 0:
        _fail(
            f"row counts wrong: accepted={row['row_count_accepted']}, "
            f"rejected={row['row_count_rejected']}"
        )
    _log(
        f"batch complete: accepted={row['row_count_accepted']}, "
        f"rejected={row['row_count_rejected']}"
    )

    _tail_listener_for_pass(batch_id)

    # Cleanup the on-disk CSV so re-runs don't pile up.
    try:
        csv_path.unlink()
    except OSError:
        pass

    _log("stage-g-full live assertion: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
