# SPDX-License-Identifier: Apache-2.0
"""Run the agent pipeline on complaints that do not yet have agent_runs.

Batch ingestion is processed by the arq worker container, whose environment
does not enable the agent pipeline (it defaults off so the Prompt-11
regression suite stays green). This host-side pass closes that gap for the
demo: after a batch lands, it finds every complaint with zero ``agent_runs``
rows and runs triage -> investigation -> synthesis against them, using the
model provider selected by ``SBS_API_MODEL_PROVIDER`` (the same env var
scripts/demo.sh exports).

It is idempotent: a complaint that already has at least one agent_run is
skipped, so re-running never double-processes.

    SBS_API_MODEL_PROVIDER=mock \\
    SBS_API_DATABASE_URL=postgresql+asyncpg://sbs:sbs@localhost:5432/sbs_dev \\
        uv run python scripts/run_agent_pipeline_on_new.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "api"))

DEFAULT_DSN = "postgresql+asyncpg://sbs:sbs@localhost:5432/sbs_dev"  # pragma: allowlist secret


async def _run(limit: int | None) -> int:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.agents.orchestrator import run_agent_pipeline
    from sbs_api.agents.providers import get_provider
    from sbs_api.db.models.agent_run import AgentRun
    from sbs_api.db.models.complaint import ComplaintRecord

    dsn = os.getenv("SBS_API_DATABASE_URL", DEFAULT_DSN)
    provider = get_provider()
    engine = create_async_engine(dsn)
    SM = async_sessionmaker(engine, expire_on_commit=False)

    print("== run_agent_pipeline_on_new.py ==")
    print(f"DSN: {dsn}")
    print(f"provider: {provider.name}")

    try:
        async with SM() as session:
            # Complaints with no agent_runs row yet, oldest first.
            stmt = (
                select(ComplaintRecord.complaint_id)
                .outerjoin(
                    AgentRun,
                    AgentRun.complaint_id == ComplaintRecord.complaint_id,
                )
                .where(AgentRun.complaint_id.is_(None))
                .order_by(ComplaintRecord.received_at.asc())
            )
            if limit is not None:
                stmt = stmt.limit(limit)
            new_ids = [row[0] for row in (await session.execute(stmt)).all()]

        print(f"complaints without agent_runs: {len(new_ids)}")

        processed = 0
        failed = 0
        for cid in new_ids:
            async with SM() as session:
                try:
                    result = await run_agent_pipeline(
                        session, complaint_id=cid, provider=provider
                    )
                    await session.commit()
                    processed += 1
                    print(f"  {cid}: route_to={result.route_to}")
                except Exception as exc:  # noqa: BLE001
                    await session.rollback()
                    failed += 1
                    print(f"  {cid}: FAILED — {type(exc).__name__}: {exc}")

        print(f"processed={processed} failed={failed}")
        # Tolerate individual bad complaints (e.g. a malformed legacy seed
        # row): only signal failure when there was work to do and none of
        # it succeeded, which means the pipeline itself is broken.
        if new_ids and processed == 0:
            return 1
        return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of complaints processed (default: all new).",
    )
    args = p.parse_args(argv)
    return asyncio.run(_run(args.limit))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
