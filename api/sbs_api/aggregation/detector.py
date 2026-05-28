"""Pattern-detection rules over windowed complaint buckets.

Four rule types — VOLUME_SPIKE, SUSTAINED_ELEVATION,
CROSS_SOURCE_CORRELATION, NEW_TOPIC_EMERGENCE — locked in
P-RESHAPE-2. Each rule, when it fires, emits a :class:`PatternCandidate`
carrying the bucket identity, the contributing complaint IDs (and
INDECOPI case IDs for the cross-source rule), and a *trigger margin*
(how far the actual signal overshot the rule threshold). The
:mod:`severity` module turns that margin into a composite score.

A bucket may fire **more than one** rule per tick (e.g. a sustained
elevation that just spiked). The runner persists every candidate so
the cockpit can render them independently.

These rules are deterministic and pure: no LLM, no agents, no
randomness. The same input bucket always produces the same candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from sbs_api.aggregation.windower import BucketWindow, FraudWindow


# Locked rule thresholds. Names match the rule description in
# docs/sessions/2026-05-27 P-RESHAPE-2.
VOLUME_SPIKE_MIN_COUNT_24H = 3
VOLUME_SPIKE_RATIO = 2.5
VOLUME_SPIKE_PRIOR_MEAN_FLOOR = 1.0

SUSTAINED_ELEVATION_RATIO = 1.8
SUSTAINED_ELEVATION_PRIOR_MEAN_FLOOR = 5.0

CROSS_SOURCE_COMPLAINTS_RATIO = 1.5  # ≥ 50% WoW
CROSS_SOURCE_INDECOPI_RATIO = 1.3  # ≥ 30% WoW

NEW_TOPIC_MIN_COUNT_24H = 5

# FRAUD_EMERGENCE thresholds (P-RESHAPE-6).
FRAUD_SOCIAL_MIN_72H = 5
FRAUD_COMPLAINT_MIN_24H = 3
FRAUD_INDECOPI_MIN_7D = 2


class PatternType(str, Enum):
    VOLUME_SPIKE = "VOLUME_SPIKE"
    SUSTAINED_ELEVATION = "SUSTAINED_ELEVATION"
    CROSS_SOURCE_CORRELATION = "CROSS_SOURCE_CORRELATION"
    NEW_TOPIC_EMERGENCE = "NEW_TOPIC_EMERGENCE"
    FRAUD_EMERGENCE = "FRAUD_EMERGENCE"


@dataclass(frozen=True)
class PatternCandidate:
    """One rule fired on one bucket.

    Pre-severity. The runner applies the severity scorer next and only
    persists the candidate when the resulting row is worth showing on
    the cockpit (every band lands on disk; only HIGH triggers
    Investigation).
    """

    pattern_type: PatternType
    institution_id: str
    complaint_category: str
    window: BucketWindow
    trigger_margin: float
    bucket_count_window: int
    indecopi_case_count: int
    contributing_complaint_ids: tuple[str, ...]
    contributing_indecopi_case_ids: tuple[str, ...]
    prior_baseline: float


def detect_patterns(windows: Iterable[BucketWindow]) -> list[PatternCandidate]:
    """Apply every rule to every bucket. Order is deterministic for
    audit replay: rules are evaluated in the order declared above, and
    buckets in (institution_id, complaint_category) order."""
    out: list[PatternCandidate] = []
    for bucket in sorted(
        windows,
        key=lambda b: (b.institution_id, b.complaint_category),
    ):
        candidate = _check_volume_spike(bucket)
        if candidate is not None:
            out.append(candidate)
        candidate = _check_sustained_elevation(bucket)
        if candidate is not None:
            out.append(candidate)
        candidate = _check_cross_source_correlation(bucket)
        if candidate is not None:
            out.append(candidate)
        candidate = _check_new_topic_emergence(bucket)
        if candidate is not None:
            out.append(candidate)
    return out


# ---------------------------------------------------------------------------
# Per-rule predicates
# ---------------------------------------------------------------------------


def _check_volume_spike(bucket: BucketWindow) -> PatternCandidate | None:
    if bucket.count_24h < VOLUME_SPIKE_MIN_COUNT_24H:
        return None
    if bucket.prior_7d_daily_mean < VOLUME_SPIKE_PRIOR_MEAN_FLOOR:
        return None
    actual_ratio = bucket.count_24h / bucket.prior_7d_daily_mean
    if actual_ratio < VOLUME_SPIKE_RATIO:
        return None
    margin = actual_ratio / VOLUME_SPIKE_RATIO
    return PatternCandidate(
        pattern_type=PatternType.VOLUME_SPIKE,
        institution_id=bucket.institution_id,
        complaint_category=bucket.complaint_category,
        window=bucket,
        trigger_margin=margin,
        bucket_count_window=bucket.count_24h,
        indecopi_case_count=bucket.indecopi_count_7d,
        contributing_complaint_ids=bucket.contributing_complaint_ids_24h,
        contributing_indecopi_case_ids=tuple(),
        prior_baseline=bucket.prior_7d_daily_mean,
    )


def _check_sustained_elevation(bucket: BucketWindow) -> PatternCandidate | None:
    if bucket.prior_4w_weekly_mean < SUSTAINED_ELEVATION_PRIOR_MEAN_FLOOR:
        return None
    actual_ratio = bucket.count_7d / bucket.prior_4w_weekly_mean
    if actual_ratio < SUSTAINED_ELEVATION_RATIO:
        return None
    margin = actual_ratio / SUSTAINED_ELEVATION_RATIO
    return PatternCandidate(
        pattern_type=PatternType.SUSTAINED_ELEVATION,
        institution_id=bucket.institution_id,
        complaint_category=bucket.complaint_category,
        window=bucket,
        trigger_margin=margin,
        bucket_count_window=bucket.count_7d,
        indecopi_case_count=bucket.indecopi_count_7d,
        contributing_complaint_ids=bucket.contributing_complaint_ids_7d,
        contributing_indecopi_case_ids=tuple(),
        prior_baseline=bucket.prior_4w_weekly_mean,
    )


def _check_cross_source_correlation(
    bucket: BucketWindow,
) -> PatternCandidate | None:
    # Complaints up ≥ 50% week-over-week.
    if bucket.complaints_7d_prior <= 0:
        return None
    complaints_ratio = bucket.count_7d / bucket.complaints_7d_prior
    if complaints_ratio < CROSS_SOURCE_COMPLAINTS_RATIO:
        return None
    # INDECOPI cases up ≥ 30% week-over-week in the same window.
    if bucket.indecopi_count_7d_prior <= 0:
        # No prior INDECOPI cases — treat any 7d INDECOPI activity above
        # zero as a saturating ratio so a brand-new cross-source signal
        # still fires.
        if bucket.indecopi_count_7d <= 0:
            return None
        indecopi_ratio = float("inf")
    else:
        indecopi_ratio = bucket.indecopi_count_7d / bucket.indecopi_count_7d_prior
    if indecopi_ratio < CROSS_SOURCE_INDECOPI_RATIO:
        return None
    # Trigger margin uses the **weaker** of the two ratio overshoots so
    # the severity score reflects the binding constraint.
    complaints_margin = complaints_ratio / CROSS_SOURCE_COMPLAINTS_RATIO
    if indecopi_ratio == float("inf"):
        indecopi_margin = 3.0  # treat as saturated for severity purposes
    else:
        indecopi_margin = indecopi_ratio / CROSS_SOURCE_INDECOPI_RATIO
    margin = min(complaints_margin, indecopi_margin)
    return PatternCandidate(
        pattern_type=PatternType.CROSS_SOURCE_CORRELATION,
        institution_id=bucket.institution_id,
        complaint_category=bucket.complaint_category,
        window=bucket,
        trigger_margin=margin,
        bucket_count_window=bucket.count_7d,
        indecopi_case_count=bucket.indecopi_count_7d,
        contributing_complaint_ids=bucket.contributing_complaint_ids_7d,
        contributing_indecopi_case_ids=bucket.contributing_indecopi_case_ids_7d,
        prior_baseline=float(bucket.complaints_7d_prior),
    )


def _check_new_topic_emergence(
    bucket: BucketWindow,
) -> PatternCandidate | None:
    if bucket.count_24h < NEW_TOPIC_MIN_COUNT_24H:
        return None
    if bucket.count_30d_prior != 0:
        return None
    if bucket.count_30d - bucket.count_24h > 0:
        # Activity exists in [now-30d, now-24h] for this bucket — not a
        # truly new topic, even if the 30d-prior window is clean.
        return None
    # The rule has no continuous "ratio" so we synthesise a margin from
    # how far the 24h count overshoots the 5-complaint floor.
    margin = bucket.count_24h / NEW_TOPIC_MIN_COUNT_24H
    return PatternCandidate(
        pattern_type=PatternType.NEW_TOPIC_EMERGENCE,
        institution_id=bucket.institution_id,
        complaint_category=bucket.complaint_category,
        window=bucket,
        trigger_margin=margin,
        bucket_count_window=bucket.count_24h,
        indecopi_case_count=bucket.indecopi_count_7d,
        contributing_complaint_ids=bucket.contributing_complaint_ids_24h,
        contributing_indecopi_case_ids=tuple(),
        prior_baseline=0.0,
    )


# ---------------------------------------------------------------------------
# FRAUD_EMERGENCE (P-RESHAPE-6) — per-institution, cross-source
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FraudCandidate:
    """A FRAUD_EMERGENCE detection. Scored with the LOCKED fraud-weight
    set (``severity.score_fraud_severity``), not the standard composite."""

    institution_id: str
    window: FraudWindow
    trigger_margin: float
    social_signal_count_72h: int
    fraud_complaint_count_24h: int
    indecopi_fraud_count_7d: int
    contributing_complaint_ids: tuple[str, ...]
    contributing_social_signal_ids: tuple[str, ...]
    contributing_indecopi_case_ids: tuple[str, ...]
    detected_fraud_indicators: tuple[str, ...]


def detect_fraud_emergence(
    windows: Iterable[FraudWindow],
) -> list[FraudCandidate]:
    """FRAUD_EMERGENCE fires when, for one institution:

    * ≥ 5 fraud-indicator social signals in the last 72h, AND
    * (≥ 3 fraud-category complaints in 24h OR ≥ 2 fraud INDECOPI in 7d)

    The trigger margin is how far the social-signal floor was overshot
    (the social feed is the leading indicator that defines the rule)."""
    out: list[FraudCandidate] = []
    for w in sorted(windows, key=lambda x: x.institution_id):
        if w.social_signal_count_72h < FRAUD_SOCIAL_MIN_72H:
            continue
        complaint_arm = w.fraud_complaint_count_24h >= FRAUD_COMPLAINT_MIN_24H
        indecopi_arm = w.indecopi_fraud_count_7d >= FRAUD_INDECOPI_MIN_7D
        if not (complaint_arm or indecopi_arm):
            continue
        margin = w.social_signal_count_72h / FRAUD_SOCIAL_MIN_72H
        out.append(
            FraudCandidate(
                institution_id=w.institution_id,
                window=w,
                trigger_margin=margin,
                social_signal_count_72h=w.social_signal_count_72h,
                fraud_complaint_count_24h=w.fraud_complaint_count_24h,
                indecopi_fraud_count_7d=w.indecopi_fraud_count_7d,
                contributing_complaint_ids=w.contributing_complaint_ids_24h,
                contributing_social_signal_ids=w.contributing_social_signal_ids_72h,
                contributing_indecopi_case_ids=w.contributing_indecopi_case_ids_7d,
                detected_fraud_indicators=w.detected_fraud_indicators,
            )
        )
    return out
