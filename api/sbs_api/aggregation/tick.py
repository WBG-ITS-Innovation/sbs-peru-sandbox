"""Aggregation tick — orchestrates windower → detector → severity → persist.

One :func:`run_aggregation_tick` call runs the pipeline once. The
returned :class:`TickResult` lists the pattern IDs inserted this tick;
the caller (the arq cron job, or an integration test) feeds those IDs
into :func:`sbs_api.agents.orchestrator.run_investigation_from_pattern`.

The tick is **deterministic** and **idempotent at the pattern key
level**: re-running against the same data produces patterns with the
same logical identity (same institution + category + pattern_type +
window_end). The persistence layer uses an upsert keyed on those four
fields so a repeat tick does not duplicate rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.aggregation.detector import (
    PatternCandidate,
    PatternType,
    detect_fraud_emergence,
    detect_patterns,
)
from sbs_api.aggregation.severity import (
    HIGH_THRESHOLD,
    FraudSeverityInputs,
    SeverityBand,
    SeverityInputs,
    score_fraud_severity,
    score_severity,
)
from sbs_api.aggregation.windower import (
    WINDOW_24H,
    WINDOW_7D,
    WINDOW_72H,
    build_fraud_windows,
    build_windows,
)
from sbs_api.db.models.pattern_detection import PatternDetection
from sbs_api.observability.logging import get_logger

_logger = get_logger(__name__)


@dataclass(frozen=True)
class TickResult:
    """Summary of one tick — what landed, what fired HIGH."""

    candidates_evaluated: int
    rows_inserted: int
    rows_reused: int
    high_pattern_ids: tuple[str, ...]


def _window_bounds(pattern_type: PatternType, now: datetime) -> tuple[datetime, datetime]:
    """Pattern-type-specific (window_start, window_end). 24h-class rules
    record the 24h window; the other three record 7d."""
    if pattern_type in {PatternType.VOLUME_SPIKE, PatternType.NEW_TOPIC_EMERGENCE}:
        return now - WINDOW_24H, now
    return now - WINDOW_7D, now


def _pattern_key(c: PatternCandidate, window_end: datetime) -> tuple[str, str, str, datetime]:
    """Logical identity of a pattern for idempotency. Re-running the
    tick against the same data must not double-insert."""
    return (c.institution_id, c.complaint_category, c.pattern_type.value, window_end)


async def run_aggregation_tick(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> TickResult:
    """One pass: window → detect → score → persist.

    Pass an explicit ``now`` from tests so the windowing is
    deterministic against seeded ``received_at`` values.
    """
    now = now or datetime.now(tz=timezone.utc)
    windows = await build_windows(session, now=now)
    candidates = detect_patterns(windows)

    # FRAUD_EMERGENCE — per-institution cross-source rule (P-RESHAPE-6).
    fraud_windows = await build_fraud_windows(session, now=now)
    fraud_candidates = detect_fraud_emergence(fraud_windows)

    high_pattern_ids: list[str] = []
    rows_inserted = 0
    rows_reused = 0

    for candidate in candidates:
        window_start, window_end = _window_bounds(candidate.pattern_type, now)
        severity = score_severity(
            SeverityInputs(
                bucket_count_window=candidate.bucket_count_window,
                indecopi_case_count=candidate.indecopi_case_count,
                trigger_margin=candidate.trigger_margin,
                prior_baseline=candidate.prior_baseline,
            )
        )

        existing = (
            await session.execute(
                select(PatternDetection).where(
                    PatternDetection.institution_code == candidate.institution_id,
                    PatternDetection.complaint_category == candidate.complaint_category,
                    PatternDetection.pattern_type == candidate.pattern_type.value,
                    PatternDetection.window_end == window_end,
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            rows_reused += 1
            if (
                existing.severity_band == SeverityBand.HIGH.value
                and not existing.triggered_investigation
            ):
                high_pattern_ids.append(existing.pattern_id)
            continue

        pattern_id = str(uuid.uuid4())
        row = PatternDetection(
            pattern_id=pattern_id,
            detected_at=now,
            window_start=window_start,
            window_end=window_end,
            institution_code=candidate.institution_id,
            complaint_category=candidate.complaint_category,
            pattern_type=candidate.pattern_type.value,
            severity_score=severity.score,
            severity_band=severity.band.value,
            contributing_complaint_ids=list(candidate.contributing_complaint_ids),
            contributing_indecopi_case_ids=(
                list(candidate.contributing_indecopi_case_ids)
                if candidate.contributing_indecopi_case_ids
                else None
            ),
            composite_breakdown=severity.to_breakdown(),
            triggered_investigation=False,
            investigation_run_id=None,
        )
        session.add(row)
        rows_inserted += 1
        if severity.band == SeverityBand.HIGH:
            high_pattern_ids.append(pattern_id)

    # --- FRAUD_EMERGENCE rows (scored with the LOCKED fraud-weight set) ---
    window_start_72h = now - WINDOW_72H
    for fc in fraud_candidates:
        severity = score_fraud_severity(
            FraudSeverityInputs(
                social_signal_count_72h=fc.social_signal_count_72h,
                fraud_complaint_count_24h=fc.fraud_complaint_count_24h,
                indecopi_fraud_count_7d=fc.indecopi_fraud_count_7d,
                trigger_margin=fc.trigger_margin,
            )
        )
        existing = (
            await session.execute(
                select(PatternDetection).where(
                    PatternDetection.institution_code == fc.institution_id,
                    PatternDetection.complaint_category == "FRAUD",
                    PatternDetection.pattern_type
                    == PatternType.FRAUD_EMERGENCE.value,
                    PatternDetection.window_end == now,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            rows_reused += 1
            if (
                existing.severity_band == SeverityBand.HIGH.value
                and not existing.triggered_investigation
            ):
                high_pattern_ids.append(existing.pattern_id)
            continue

        breakdown = severity.to_breakdown()
        # Carry the social signal ids + fraud indicators in the breakdown
        # so the sector-broadcast agent can read them without a re-query.
        breakdown["social_signal_ids"] = list(fc.contributing_social_signal_ids)
        breakdown["threat_indicators"] = list(fc.detected_fraud_indicators)

        pattern_id = str(uuid.uuid4())
        row = PatternDetection(
            pattern_id=pattern_id,
            detected_at=now,
            window_start=window_start_72h,
            window_end=now,
            institution_code=fc.institution_id,
            complaint_category="FRAUD",  # cross-category aggregate label
            pattern_type=PatternType.FRAUD_EMERGENCE.value,
            severity_score=severity.score,
            severity_band=severity.band.value,
            contributing_complaint_ids=list(fc.contributing_complaint_ids),
            contributing_indecopi_case_ids=(
                list(fc.contributing_indecopi_case_ids)
                if fc.contributing_indecopi_case_ids
                else None
            ),
            composite_breakdown=breakdown,
            triggered_investigation=False,
            investigation_run_id=None,
        )
        session.add(row)
        rows_inserted += 1
        if severity.band == SeverityBand.HIGH:
            high_pattern_ids.append(pattern_id)

    await session.flush()

    total_candidates = len(candidates) + len(fraud_candidates)
    _logger.info(
        "aggregation tick complete",
        extra={
            "candidates": total_candidates,
            "fraud_candidates": len(fraud_candidates),
            "rows_inserted": rows_inserted,
            "rows_reused": rows_reused,
            "high_count": len(high_pattern_ids),
        },
    )

    return TickResult(
        candidates_evaluated=total_candidates,
        rows_inserted=rows_inserted,
        rows_reused=rows_reused,
        high_pattern_ids=tuple(high_pattern_ids),
    )


# arq function entry point. Imports DB sessionmaker lazily so unit
# tests can import this module without standing up Postgres.
async def aggregation_tick_job(ctx: dict) -> dict:  # pragma: no cover - arq entry
    """``arq`` cron-job entry. Opens a session, runs one tick, returns
    a JSON-serialisable summary (arq logs the return value)."""
    from sbs_api.agents.orchestrator import run_investigation_from_pattern
    from sbs_api.db.session import get_sessionmaker

    SessionMaker = get_sessionmaker()
    async with SessionMaker() as session:
        result = await run_aggregation_tick(session)
        for pattern_id in result.high_pattern_ids:
            await run_investigation_from_pattern(session, pattern_id=pattern_id)
        await session.commit()
    return {
        "candidates": result.candidates_evaluated,
        "inserted": result.rows_inserted,
        "reused": result.rows_reused,
        "high_count": len(result.high_pattern_ids),
        "high_threshold": HIGH_THRESHOLD,
    }
