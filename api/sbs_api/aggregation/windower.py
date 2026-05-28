"""Rolling-window bucket counts for the aggregation tick.

Given the current tick time ``now``, this module emits one
:class:`BucketWindow` per (institution_id, complaint_category) pair
that has any non-zero activity inside the lookback windows the
detector rules need:

* 24-hour count: complaints in ``[now - 24h, now]``
* 7-day count: complaints in ``[now - 7d, now]``
* 30-day count (used by NEW_TOPIC_EMERGENCE): complaints in
  ``[now - 30d, now]``
* prior 7d daily mean: mean per-day count over ``[now - 8d, now - 1d]``
  (avoids double-counting the live 24h window)
* prior 4-week mean: mean per-week count over the four weeks
  *preceding* the live 7d window
* INDECOPI case counts in the live 7d window and the *prior* 7d
  window (used by CROSS_SOURCE_CORRELATION)

The query is a single pass per category over ``complaints`` and one
pass over ``indecopi_cases``. We deliberately read all complaints once
per tick rather than precomputing materialised aggregates — at sandbox
scale the table is small, and the audit chain wants a deterministic
read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.indecopi_case import IndecopiCase


WINDOW_24H = timedelta(hours=24)
WINDOW_7D = timedelta(days=7)
WINDOW_30D = timedelta(days=30)
WINDOW_8D = timedelta(days=8)
WINDOW_28D = timedelta(days=28)
WINDOW_35D = timedelta(days=35)
WINDOW_14D = timedelta(days=14)
WINDOW_72H = timedelta(hours=72)

# Fraud / unauthorised-operation motivo categories for FRAUD_EMERGENCE.
# Covers both the canonical Anexo 1-A codes and the lowercase names the
# P-RESHAPE prompts use, so the rule fires regardless of which form a
# seed or live row carries. Kept here (not in the detector) because the
# fraud windower needs it to scope its complaint + INDECOPI counts.
FRAUD_CATEGORIES = frozenset(
    {
        "OPERACION_NO_RECONOCIDA",
        "COBRO_INDEBIDO",
        "fraude",
        "transferencia_no_autorizada",
        "cargos_no_reconocidos",
        "comisiones_no_divulgadas",
    }
)


@dataclass(frozen=True)
class BucketWindow:
    """All counts a detector rule may need, for one (institution, category)."""

    institution_id: str
    complaint_category: str
    now: datetime
    count_24h: int
    count_7d: int
    count_30d: int
    count_30d_prior: int
    prior_7d_daily_mean: float
    prior_4w_weekly_mean: float
    complaints_7d_prior: int
    indecopi_count_7d: int
    indecopi_count_7d_prior: int
    contributing_complaint_ids_24h: tuple[str, ...]
    contributing_complaint_ids_7d: tuple[str, ...]
    contributing_indecopi_case_ids_7d: tuple[str, ...]


async def build_windows(
    session: AsyncSession, *, now: datetime
) -> list[BucketWindow]:
    """Read the complaints + indecopi_cases tables once and emit one
    :class:`BucketWindow` per active (institution, category) bucket.

    "Active" = any complaint inside the last 35 days OR any INDECOPI
    case inside the last 14 days. Anything older is irrelevant to the
    detector rules.
    """
    cutoff = now - WINDOW_35D
    rows = (
        await session.execute(
            select(ComplaintRecord).where(ComplaintRecord.received_at >= cutoff)
        )
    ).scalars().all()

    indecopi_rows = (
        await session.execute(
            select(IndecopiCase).where(
                IndecopiCase.opened_at >= now - WINDOW_14D
            )
        )
    ).scalars().all()

    # Bucket complaints by (institution, category)
    buckets: dict[tuple[str, str], list[ComplaintRecord]] = {}
    for c in rows:
        key = (c.institution_id, _category_of(c))
        buckets.setdefault(key, []).append(c)

    indecopi_by_key: dict[tuple[str, str], list[IndecopiCase]] = {}
    for ic in indecopi_rows:
        indecopi_by_key.setdefault((ic.institution_id, ic.complaint_category), []).append(ic)

    out: list[BucketWindow] = []
    seen_keys: set[tuple[str, str]] = set()
    for key in list(buckets.keys()) + list(indecopi_by_key.keys()):
        if key in seen_keys:
            continue
        seen_keys.add(key)
        institution_id, category = key
        bucket = buckets.get(key, [])
        ind = indecopi_by_key.get(key, [])
        out.append(
            _summarise_bucket(
                institution_id=institution_id,
                complaint_category=category,
                now=now,
                complaints=bucket,
                indecopi_cases=ind,
            )
        )
    return out


def _category_of(c: ComplaintRecord) -> str:
    """Resolve the complaint's aggregation category.

    The aggregation layer keys on the canonical Annex 1-A ``motivo_code``
    (the complaint's *reason* class). The institution-supplied product
    category is recorded on the row but is not the aggregation pivot —
    Jorge's team groups complaints by why the user is unhappy, not by
    which product they hold.
    """
    return c.motivo_code or "UNCATEGORISED"


def _summarise_bucket(
    *,
    institution_id: str,
    complaint_category: str,
    now: datetime,
    complaints: Iterable[ComplaintRecord],
    indecopi_cases: Iterable[Any],
) -> BucketWindow:
    complaints_list = list(complaints)
    indecopi_list = list(indecopi_cases)

    in_24h: list[ComplaintRecord] = []
    in_7d: list[ComplaintRecord] = []
    in_30d: list[ComplaintRecord] = []
    in_prior_30d: list[ComplaintRecord] = []
    in_prior_7d: list[ComplaintRecord] = []
    in_prior_4w: list[ComplaintRecord] = []

    for c in complaints_list:
        ts = c.received_at
        delta = now - ts
        if delta <= WINDOW_24H:
            in_24h.append(c)
        if delta <= WINDOW_7D:
            in_7d.append(c)
        else:
            # 7d-prior window for the cross-source rule
            if delta <= WINDOW_14D:
                in_prior_7d.append(c)
        if delta <= WINDOW_30D:
            in_30d.append(c)
        else:
            if delta <= timedelta(days=60):
                in_prior_30d.append(c)

        # Prior-day 7-day mean: complaints in [now-8d, now-1d]
        if WINDOW_24H < delta <= WINDOW_8D:
            pass  # captured via in_7d above; mean computed below

        # Prior 4-week mean: complaints in [now-35d, now-7d]
        if WINDOW_7D < delta <= WINDOW_35D:
            in_prior_4w.append(c)

    # Prior 7d daily mean = (count in [now-8d, now-1d]) / 7
    prior_7d_count = 0
    lower = now - WINDOW_8D
    upper = now - WINDOW_24H
    for c in complaints_list:
        if lower < c.received_at <= upper:
            prior_7d_count += 1
    prior_7d_daily_mean = prior_7d_count / 7.0

    # Prior 4-week weekly mean = (count in [now-35d, now-7d]) / 4
    prior_4w_weekly_mean = len(in_prior_4w) / 4.0

    indecopi_count_7d = 0
    indecopi_count_7d_prior = 0
    ind_ids_7d: list[str] = []
    for ic in indecopi_list:
        opened_delta = now - ic.opened_at
        if opened_delta <= WINDOW_7D:
            indecopi_count_7d += 1
            ind_ids_7d.append(ic.case_id)
        elif opened_delta <= WINDOW_14D:
            indecopi_count_7d_prior += 1

    return BucketWindow(
        institution_id=institution_id,
        complaint_category=complaint_category,
        now=now,
        count_24h=len(in_24h),
        count_7d=len(in_7d),
        count_30d=len(in_30d),
        count_30d_prior=len(in_prior_30d),
        prior_7d_daily_mean=prior_7d_daily_mean,
        prior_4w_weekly_mean=prior_4w_weekly_mean,
        complaints_7d_prior=len(in_prior_7d),
        indecopi_count_7d=indecopi_count_7d,
        indecopi_count_7d_prior=indecopi_count_7d_prior,
        contributing_complaint_ids_24h=tuple(c.complaint_id for c in in_24h),
        contributing_complaint_ids_7d=tuple(c.complaint_id for c in in_7d),
        contributing_indecopi_case_ids_7d=tuple(ind_ids_7d),
    )


# Late import to keep ``Any`` available in the signature without forcing
# every caller to import IndecopiCase. The ORM model is defined alongside
# PatternDetection.
from typing import Any  # noqa: E402


# ---------------------------------------------------------------------------
# Fraud-emergence windows (P-RESHAPE-6)
# ---------------------------------------------------------------------------
#
# FRAUD_EMERGENCE aggregates per-INSTITUTION (across all fraud categories),
# not per (institution, category) bucket — so it gets its own window
# builder. It fuses three feeds: social signals (72h), fraud-category
# complaints (24h), and fraud-category INDECOPI cases (7d).


@dataclass(frozen=True)
class FraudWindow:
    institution_id: str
    now: datetime
    social_signal_count_72h: int
    fraud_complaint_count_24h: int
    indecopi_fraud_count_7d: int
    contributing_complaint_ids_24h: tuple[str, ...]
    contributing_social_signal_ids_72h: tuple[str, ...]
    contributing_indecopi_case_ids_7d: tuple[str, ...]
    detected_fraud_indicators: tuple[str, ...]


async def build_fraud_windows(
    session: AsyncSession, *, now: datetime
) -> list[FraudWindow]:
    """One FraudWindow per institution that has any social signal in the
    last 72h. (Social presence is the necessary condition for
    FRAUD_EMERGENCE, so institutions with no social signal are skipped.)"""
    from sbs_api.db.models.social_signal import SocialSignal

    social_cutoff = now - WINDOW_72H
    signals = (
        await session.execute(
            select(SocialSignal).where(SocialSignal.captured_at >= social_cutoff)
        )
    ).scalars().all()

    # Group social signals by institution (a signal may mention several).
    social_by_inst: dict[str, list[SocialSignal]] = {}
    for sig in signals:
        # Only signals carrying a fraud indicator count toward the rule.
        if not sig.detected_fraud_indicators:
            continue
        for inst in sig.detected_institution_codes or []:
            social_by_inst.setdefault(inst, []).append(sig)

    if not social_by_inst:
        return []

    # Complaints in the fraud categories, last 24h, for the candidate FIs.
    complaint_cutoff = now - WINDOW_24H
    inst_ids = list(social_by_inst.keys())
    complaints = (
        await session.execute(
            select(ComplaintRecord).where(
                ComplaintRecord.institution_id.in_(inst_ids),
                ComplaintRecord.received_at > complaint_cutoff,
            )
        )
    ).scalars().all()
    fraud_complaints_by_inst: dict[str, list[ComplaintRecord]] = {}
    for c in complaints:
        if (c.motivo_code or "") in FRAUD_CATEGORIES:
            fraud_complaints_by_inst.setdefault(c.institution_id, []).append(c)

    # INDECOPI fraud cases, last 7d.
    indecopi_cutoff = now - WINDOW_7D
    indecopi = (
        await session.execute(
            select(IndecopiCase).where(
                IndecopiCase.institution_id.in_(inst_ids),
                IndecopiCase.opened_at > indecopi_cutoff,
            )
        )
    ).scalars().all()
    indecopi_by_inst: dict[str, list[IndecopiCase]] = {}
    for ic in indecopi:
        if (ic.complaint_category or "") in FRAUD_CATEGORIES:
            indecopi_by_inst.setdefault(ic.institution_id, []).append(ic)

    out: list[FraudWindow] = []
    for inst_id in sorted(social_by_inst.keys()):
        sigs = social_by_inst[inst_id]
        fcs = fraud_complaints_by_inst.get(inst_id, [])
        ics = indecopi_by_inst.get(inst_id, [])
        indicators: set[str] = set()
        for s in sigs:
            indicators.update(s.detected_fraud_indicators or [])
        out.append(
            FraudWindow(
                institution_id=inst_id,
                now=now,
                social_signal_count_72h=len(sigs),
                fraud_complaint_count_24h=len(fcs),
                indecopi_fraud_count_7d=len(ics),
                contributing_complaint_ids_24h=tuple(c.complaint_id for c in fcs),
                contributing_social_signal_ids_72h=tuple(s.signal_id for s in sigs),
                contributing_indecopi_case_ids_7d=tuple(ic.case_id for ic in ics),
                detected_fraud_indicators=tuple(sorted(indicators)),
            )
        )
    return out
