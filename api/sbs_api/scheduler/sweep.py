# SPDX-License-Identifier: Apache-2.0
"""Idempotency-record sweep job — ADR 0029.

Deletes ``idempotency_records`` rows where ``expires_at`` is older than
``now() - grace`` (default 5 minutes of grace so a row that is expiring
this exact second is not raced against a concurrent read).

Emits a structlog event ``idempotency.sweep.completed`` per run with the
rows-deleted count, the elapsed duration, and a synthetic correlation_id
so a log query can reconstruct which sweep run touched which rows.

The job runs on the FastAPI process's asyncio loop — no Celery, no
external queue. APScheduler's ``AsyncIOScheduler`` is the minimum
plausible scheduler that interleaves cleanly with FastAPI's lifespan.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sbs_api.config import get_settings
from sbs_api.db.models.idempotency import IdempotencyRecord
from sbs_api.observability.logging import get_logger

_logger = get_logger(__name__)


@dataclass(frozen=True)
class SweepResult:
    """Returned by :func:`sweep_expired_idempotency_records` for tests."""

    deleted_count: int
    duration_ms: float
    correlation_id: str


async def sweep_expired_idempotency_records(
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    grace_seconds: int | None = None,
    correlation_id: str | None = None,
) -> SweepResult:
    """Delete expired idempotency rows and return the count.

    Pure DB-side DELETE; no row-by-row processing. The grace window
    defaults to the value from :class:`Settings` so a caller that
    overrides Settings in tests sees the right behaviour.
    """

    settings = get_settings()
    grace = grace_seconds if grace_seconds is not None else settings.idempotency_sweep_grace_seconds
    cid = correlation_id or f"sweep-{uuid.uuid4().hex[:12]}"

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=grace)
    started = time.monotonic()
    async with sessionmaker() as session:
        async with session.begin():
            # Only delete rows that have reached state='complete'. A
            # row stuck in state='processing' past its TTL is an
            # orphaned-handler signal that ops should investigate
            # (e.g. crash mid-write); deleting it would let a
            # subsequent retry create a duplicate, and would also let
            # a still-running handler's mark_complete UPDATE no-op
            # silently (the row would be gone). Orphan reaping is a
            # Day-2 admin-endpoint deliverable; sweep stays narrow.
            stmt = delete(IdempotencyRecord).where(
                IdempotencyRecord.expires_at < cutoff,
                IdempotencyRecord.state == "complete",
            )
            result = await session.execute(stmt)
            deleted = result.rowcount or 0

            # Surface orphaned processing rows separately so the
            # operator alert hook in observability has something to
            # bind to. Counted but not deleted here.
            from sqlalchemy import select, func

            orphan_stmt = (
                select(func.count())
                .select_from(IdempotencyRecord)
                .where(
                    IdempotencyRecord.expires_at < cutoff,
                    IdempotencyRecord.state == "processing",
                )
            )
            orphan_count = int((await session.execute(orphan_stmt)).scalar() or 0)
    duration_ms = (time.monotonic() - started) * 1000.0

    _logger.info(
        "idempotency.sweep.completed",
        deleted_count=deleted,
        orphan_processing_count=orphan_count,
        duration_ms=duration_ms,
        cutoff=cutoff.isoformat(),
        grace_seconds=grace,
        correlation_id=cid,
    )
    return SweepResult(
        deleted_count=deleted,
        duration_ms=duration_ms,
        correlation_id=cid,
    )
