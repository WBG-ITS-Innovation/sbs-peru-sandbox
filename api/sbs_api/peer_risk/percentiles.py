# SPDX-License-Identifier: Apache-2.0
"""Peer-percentile computation.

For a given institution + motivo_code + window, the prototype counts
complaints (no per-FI portfolio_value column exists yet; the prompt
calls for "complaints per S/.M" normalisation, but the canonical
table does not carry portfolio value, so we adapt to **raw counts**
and document the gap). Counts for every peer in the same cohort are
collected, the institution's own count is positioned against that
distribution, and the result carries percentile + z-score +
``is_outlier`` (percentile ≥ 90 OR z-score ≥ 2.0).

The compute path is real SQL + numpy. No stubbing. The function
returns an :class:`PercentileResult` even when the cohort is empty
(``cohort_size = 0``, ``percentile = None``) so callers can decide
whether to surface the analysis or label it as low-confidence.

The "sustained_days_above_p90" companion function answers the
follow-up question "how many of the last 30 days was this institution
above the cohort's p90?" — required by the PRR narrative.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.institution import InstitutionRecord
from sbs_api.peer_risk.cohorts import Cohort, assign_cohort


@dataclass(frozen=True)
class PercentileResult:
    institution_id: str
    motivo_code: str
    window_days: int
    cohort_id: str
    cohort_size: int
    self_count: int
    cohort_counts: tuple[int, ...]
    percentile: float | None
    z_score: float | None
    cohort_median: float | None
    cohort_p90: float | None
    is_outlier: bool
    sustained_days_above_p90: int


async def _bucket_counts(
    session: AsyncSession,
    *,
    institution_ids: Sequence[str],
    motivo_code: str,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, int]:
    """One pass over the complaints table; returns count by
    institution_id for every id in ``institution_ids`` (zero-filled)."""
    if not institution_ids:
        return {}
    rows = (
        await session.execute(
            select(
                ComplaintRecord.institution_id,
                func.count(),
            )
            .where(
                ComplaintRecord.institution_id.in_(list(institution_ids)),
                ComplaintRecord.motivo_code == motivo_code,
                ComplaintRecord.received_at > window_start,
                ComplaintRecord.received_at <= window_end,
            )
            .group_by(ComplaintRecord.institution_id)
        )
    ).all()
    counts = {iid: 0 for iid in institution_ids}
    for iid, n in rows:
        counts[iid] = int(n or 0)
    return counts


async def _cohort_peers(
    session: AsyncSession, *, cohort: Cohort
) -> list[InstitutionRecord]:
    """All institutions whose metadata maps to ``cohort.cohort_id`` —
    including the focal one. Pulls the small ``institutions`` table
    once and filters in Python because cohort_id is not stored on the
    row (it is derived) and we want every cohort change (new tier,
    renamed display_name) to take effect on the next tick without a
    backfill."""
    rows = (await session.execute(select(InstitutionRecord))).scalars().all()
    out: list[InstitutionRecord] = []
    for r in rows:
        try:
            peer_cohort = assign_cohort(
                display_name=r.display_name,
                tier_classification=r.tier_classification,
            )
        except Exception:  # noqa: BLE001 — skip ill-formed records, never raise
            continue
        if peer_cohort.cohort_id == cohort.cohort_id:
            out.append(r)
    return out


def _percentile_of(value: int, distribution: Sequence[int]) -> float | None:
    """Position of ``value`` against ``distribution`` (incl. self), 0–100.
    Returns ``None`` for an empty distribution."""
    if not distribution:
        return None
    arr = np.asarray(distribution, dtype=float)
    # Use the inclusive-rank percentile so a max value lands at 100.
    below = float(np.sum(arr < value))
    equal = float(np.sum(arr == value))
    rank = below + 0.5 * equal
    return round(100.0 * rank / len(arr), 2)


def _z_score(value: int, distribution: Sequence[int]) -> float | None:
    if not distribution:
        return None
    arr = np.asarray(distribution, dtype=float)
    sigma = float(arr.std(ddof=0))
    if sigma == 0:
        return None
    return round(float((value - arr.mean()) / sigma), 3)


async def _sustained_days_above_p90(
    session: AsyncSession,
    *,
    institution_id: str,
    cohort: Cohort,
    motivo_code: str,
    now: datetime,
    days: int = 30,
) -> int:
    """For each of the last ``days`` 24-hour buckets, compute the
    cohort's p90 daily count for ``motivo_code`` and tally how many
    of those days the focal institution exceeded it.

    One pass over the complaints table; the per-day grouping happens
    in Python because Postgres date-truncation on a moving window is
    awkward to write portably and the table is small at sandbox
    scale.
    """
    window_start = now - timedelta(days=days)
    peers = await _cohort_peers(session, cohort=cohort)
    peer_ids = [p.institution_id for p in peers]
    if institution_id not in peer_ids:
        peer_ids.append(institution_id)

    rows = (
        await session.execute(
            select(
                ComplaintRecord.institution_id,
                ComplaintRecord.received_at,
            ).where(
                ComplaintRecord.institution_id.in_(peer_ids),
                ComplaintRecord.motivo_code == motivo_code,
                ComplaintRecord.received_at > window_start,
                ComplaintRecord.received_at <= now,
            )
        )
    ).all()

    # Bucket by (iid, day_offset). day_offset = days since (now - days).
    daily: dict[tuple[str, int], int] = {}
    for iid, received_at in rows:
        day_offset = (now - received_at).days
        if 0 <= day_offset < days:
            key = (iid, day_offset)
            daily[key] = daily.get(key, 0) + 1

    sustained = 0
    for offset in range(days):
        peer_counts = [daily.get((iid, offset), 0) for iid in peer_ids if iid != institution_id]
        if not peer_counts:
            continue
        p90 = float(np.percentile(peer_counts, 90))
        self_count = daily.get((institution_id, offset), 0)
        if self_count > p90 and self_count > 0:
            sustained += 1
    return sustained


async def compute_peer_percentile(
    session: AsyncSession,
    *,
    institution_id: str,
    motivo_code: str,
    cohort: Cohort,
    now: datetime,
    window_days: int = 7,
) -> PercentileResult:
    """Return where ``institution_id`` sits inside its cohort for
    ``motivo_code`` over the last ``window_days`` days."""
    window_start = now - timedelta(days=window_days)
    peers = await _cohort_peers(session, cohort=cohort)
    peer_ids = [p.institution_id for p in peers]
    if institution_id not in peer_ids:
        peer_ids.append(institution_id)

    counts = await _bucket_counts(
        session,
        institution_ids=peer_ids,
        motivo_code=motivo_code,
        window_start=window_start,
        window_end=now,
    )
    self_count = counts.get(institution_id, 0)
    cohort_counts = tuple(counts.values())
    cohort_size = len(cohort_counts)

    percentile = _percentile_of(self_count, cohort_counts)
    z = _z_score(self_count, cohort_counts)

    median = None
    p90 = None
    if cohort_counts:
        median = float(np.percentile(cohort_counts, 50))
        p90 = float(np.percentile(cohort_counts, 90))

    sustained = await _sustained_days_above_p90(
        session,
        institution_id=institution_id,
        cohort=cohort,
        motivo_code=motivo_code,
        now=now,
    )

    is_outlier = bool(
        (percentile is not None and percentile >= 90.0)
        or (z is not None and z >= 2.0)
    )

    return PercentileResult(
        institution_id=institution_id,
        motivo_code=motivo_code,
        window_days=window_days,
        cohort_id=cohort.cohort_id,
        cohort_size=cohort_size,
        self_count=self_count,
        cohort_counts=cohort_counts,
        percentile=percentile,
        z_score=z,
        cohort_median=round(median, 3) if median is not None else None,
        cohort_p90=round(p90, 3) if p90 is not None else None,
        is_outlier=is_outlier,
        sustained_days_above_p90=sustained,
    )
