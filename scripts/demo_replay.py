"""Demo replay orchestrator — three institutions, deterministic seed.

Invoked from ``scripts/demo.sh``. For each of the three demo
institutions, the orchestrator:

1. Picks the institution's CSV file from the generated corpus.
2. Computes its SHA-256, inserts a batch row in state=pending into
   the live Postgres, places the CSV on disk under ``data/batches/``.
3. Enqueues ``process_batch`` onto the live arq Redis pool.
4. Polls the batch row until status == ``complete`` or ``failed``
   (timeout: ``--max-wait`` seconds).
5. Tails the webhook-listener container's log and asserts a PASS
   line is present referencing the batch_id.

Writes ``summary.json`` to ``--out-dir`` with per-batch results.

Mirrors ``scripts/smoke_stage_g_live.py`` but loops over three
institutions and reads pre-generated synthetic CSVs instead of
hand-building a 3-row payload.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "api"))

import asyncpg  # noqa: E402
from arq.connections import RedisSettings, create_pool  # noqa: E402

LIVE_DSN = "postgresql://sbs:sbs@localhost:5432/sbs_dev"  # pragma: allowlist secret
WEBHOOK_STATE = REPO_ROOT / "webhook-state" / "ready"
STORAGE_DIR = REPO_ROOT / "data" / "batches"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# The corpus generator writes each institution's CSV to
# ``<corpus-dir>/<institution_id>/<institution_id>.csv`` per
# scripts/generate-synthetic-corpus.py.
def _corpus_csv_for(corpus_dir: pathlib.Path, institution_id: str) -> pathlib.Path:
    return corpus_dir / institution_id / f"{institution_id}.csv"


def _ts() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")


def _log(msg: str) -> None:
    print(f"[{_ts()}] {msg}", flush=True)


def _new_batch_id() -> str:
    import secrets
    import uuid_utils

    base = str(uuid_utils.uuid7()).replace("-", "")
    return f"batch_{base[:24]}{secrets.token_hex(2)}"


async def _wait_for_listener_ready(timeout_s: int = 15) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if WEBHOOK_STATE.exists():
            _log(f"listener ready: {WEBHOOK_STATE.read_text().strip()}")
            return
        await asyncio.sleep(1)
    raise SystemExit(
        f"webhook-listener did not write {WEBHOOK_STATE} within {timeout_s}s"
    )


async def _insert_batch_row(
    *,
    batch_id: str,
    institution_id: str,
    sha256_hex: str,
    row_count: int,
    file_name: str,
) -> None:
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
            institution_id,
            file_name,
            dt.date(2026, 5, 1),
            dt.date(2026, 5, 31),
            "v0.1.0",
            row_count,
            sha256_hex,
            file_name,
        )
    finally:
        await conn.close()


async def _poll_batch_until_terminal(batch_id: str, timeout_s: int) -> dict:
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
            raise SystemExit(f"batch {batch_id} not found in DB")
        status = row["status"]
        if status != last_status:
            _log(f"  {batch_id[:16]} status={status}")
            last_status = status
        if status in {"complete", "failed"}:
            return dict(row)
        await asyncio.sleep(1)
    raise SystemExit(
        f"batch {batch_id} timed out at status={last_status} after {timeout_s}s"
    )


def _tail_listener_for_pass(
    batch_id: str, since: str | None = None, timeout_s: int = 30
) -> bool:
    """Poll the webhook-listener log for ``PASS delivery_id={batch_id}``.

    ``since`` is an RFC 3339 timestamp; we pass ``--since`` to docker
    compose logs so the tail window never rolls off even at full
    scale (201 rows). The earlier implementation used ``--tail 200``,
    which silently dropped PASS lines once log volume exceeded that
    buffer — a real bug at ``--scale full``.
    """

    deadline = time.time() + timeout_s
    expected = f"PASS delivery_id={batch_id}"
    cmd = ["docker", "compose", "logs", "webhook-listener"]
    if since:
        cmd.extend(["--since", since])
    while time.time() < deadline:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if expected in result.stdout:
            return True
        time.sleep(2)
    return False


async def _enqueue_process_batch(batch_id: str) -> None:
    pool = await create_pool(RedisSettings(host="localhost", port=6379, database=0))
    try:
        await pool.enqueue_job("process_batch", batch_id)
    finally:
        await pool.aclose()


def _count_rows_in_csv(csv_path: pathlib.Path) -> int:
    """Count data rows (exclude header)."""

    with csv_path.open("rb") as fh:
        return sum(1 for _ in fh) - 1


async def _replay_one_institution(
    *,
    institution_id: str,
    csv_path: pathlib.Path,
    max_wait: int,
    since: str,
) -> dict:
    batch_id = _new_batch_id()
    payload = csv_path.read_bytes()
    sha256_hex = hashlib.sha256(payload).hexdigest()
    row_count = _count_rows_in_csv(csv_path)

    # Copy the synthetic CSV into the worker's storage directory so the
    # worker can pick it up by its file_name.
    stored = STORAGE_DIR / f"{batch_id}.csv"
    stored.write_bytes(payload)
    _log(
        f"institution={institution_id} csv={csv_path.name} rows={row_count} "
        f"sha256={sha256_hex[:16]}…"
    )

    await _insert_batch_row(
        batch_id=batch_id,
        institution_id=institution_id,
        sha256_hex=sha256_hex,
        row_count=row_count,
        file_name=f"{batch_id}.csv",
    )

    await _enqueue_process_batch(batch_id)

    row = await _poll_batch_until_terminal(batch_id, timeout_s=max_wait)
    listener_pass = _tail_listener_for_pass(batch_id, since=since, timeout_s=30)

    # Clean up the on-disk CSV (the worker still has the DB record).
    try:
        stored.unlink()
    except OSError:
        pass

    return {
        "institution_id": institution_id,
        "batch_id": batch_id,
        "csv_file": csv_path.name,
        "row_count_submitted": row_count,
        "row_count_accepted": row["row_count_accepted"],
        "row_count_rejected": row["row_count_rejected"],
        "csv_sha256": sha256_hex,
        "status": row["status"],
        "failure_reason": row["failure_reason"],
        "listener_pass": listener_pass,
    }


async def amain() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", required=True, type=pathlib.Path)
    parser.add_argument("--out-dir", required=True, type=pathlib.Path)
    parser.add_argument("--max-wait", required=True, type=int)
    parser.add_argument("--institutions", nargs="+", required=True)
    args = parser.parse_args()

    await _wait_for_listener_ready()

    started_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    results: list[dict] = []
    for inst_id in args.institutions:
        csv_path = _corpus_csv_for(args.corpus_dir, inst_id)
        if not csv_path.exists():
            _log(f"corpus CSV missing for {inst_id}: {csv_path}")
            continue
        result = await _replay_one_institution(
            institution_id=inst_id,
            csv_path=csv_path,
            max_wait=args.max_wait,
            since=started_at,
        )
        results.append(result)

    finished_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    batches_completed = sum(1 for r in results if r["status"] == "complete")
    webhook_pass_count = sum(1 for r in results if r["listener_pass"])

    summary = {
        "started_at": started_at,
        "finished_at": finished_at,
        "institutions": args.institutions,
        "batches_attempted": len(results),
        "batches_completed": batches_completed,
        "webhook_pass_count": webhook_pass_count,
        "max_wait_seconds": args.max_wait,
        "per_batch": results,
    }

    out_path = args.out_dir / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    _log(f"summary written to {out_path}")

    # Exit 0 only if every institution succeeded and every listener saw PASS.
    if batches_completed != len(args.institutions):
        _log(
            f"batches_completed={batches_completed} of expected "
            f"{len(args.institutions)}"
        )
        return 4
    if webhook_pass_count != len(args.institutions):
        _log(
            f"webhook_pass_count={webhook_pass_count} of expected "
            f"{len(args.institutions)}"
        )
        return 4
    return 0


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    sys.exit(main())
