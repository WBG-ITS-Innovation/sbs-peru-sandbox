"""Composite severity scoring for pattern detections.

The five channel weights are **locked** at the sprint level and shared
with the per-complaint anomaly tool (``compute_anomaly_score``):

    indecopi  0.30
    sentiment 0.20
    narrative 0.25
    velocity  0.15
    market    0.10

Bands: HIGH ≥ 0.70, MEDIUM ≥ 0.40, LOW otherwise. Only HIGH triggers
Investigation.

Sub-scores are derived from inputs the aggregation job already has on
hand (windowed counts, INDECOPI matches, pattern trigger margin) plus
constant **proxy** values for sentiment / market — the prototype does
not run a sentiment model yet. Proxy values are recorded in the
composite_breakdown JSON so the cockpit can render them as "proxy
inputs" and audit can replay the score.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

# Locked weights, mirroring ``api/sbs_api/agents/tools/anomaly.py``.
LOCKED_WEIGHTS: dict[str, float] = {
    "indecopi": 0.30,
    "sentiment": 0.20,
    "narrative": 0.25,
    "velocity": 0.15,
    "market": 0.10,
}

HIGH_THRESHOLD = 0.70
MEDIUM_THRESHOLD = 0.40


class SeverityBand(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class SeverityInputs:
    """Raw numbers the scorer derives sub-scores from.

    All counts are window-scoped. ``trigger_margin`` is *how strongly*
    the pattern's rule fired (e.g. 6.67 for an 8-vs-1.2 spike against
    the 2.5x rule). Values above 1.0 mean the rule was overshot.
    """

    bucket_count_window: int
    indecopi_case_count: int
    trigger_margin: float
    prior_baseline: float

    def __post_init__(self) -> None:
        if self.bucket_count_window < 0:
            raise ValueError("bucket_count_window must be non-negative")
        if self.indecopi_case_count < 0:
            raise ValueError("indecopi_case_count must be non-negative")
        if self.trigger_margin < 0:
            raise ValueError("trigger_margin must be non-negative")


@dataclass(frozen=True)
class SeverityResult:
    score: float
    band: SeverityBand
    sub_scores: dict[str, float]
    contributions: dict[str, float]
    weights: dict[str, float]
    inputs: dict[str, float]
    proxy_channels: tuple[str, ...]

    def to_breakdown(self) -> dict[str, Any]:
        """JSON-serialisable composite_breakdown payload."""
        return {
            "score": self.score,
            "band": self.band.value,
            "weights": dict(self.weights),
            "sub_scores": dict(self.sub_scores),
            "contributions": dict(self.contributions),
            "inputs": dict(self.inputs),
            "proxy_channels": list(self.proxy_channels),
        }


def _band(score: float) -> SeverityBand:
    if score >= HIGH_THRESHOLD:
        return SeverityBand.HIGH
    if score >= MEDIUM_THRESHOLD:
        return SeverityBand.MEDIUM
    return SeverityBand.LOW


def _clamp(value: float, *, lo: float = 0.0, hi: float = 1.0) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


# Sub-score derivations
# ---------------------
# Each function returns a value in [0, 1]. The narrative channel reflects
# how strongly the bucket signals a coherent issue; the velocity channel
# reflects acceleration over baseline; the indecopi channel reflects
# external cross-source corroboration; sentiment and market are constant
# proxies (no upstream model yet — flagged in ``proxy_channels``).


def _indecopi_subscore(indecopi_case_count: int) -> float:
    # Five corroborating INDECOPI cases is treated as a saturated signal.
    return _clamp(indecopi_case_count / 5.0)


def _velocity_subscore(trigger_margin: float) -> float:
    # ``trigger_margin`` is the rule's overshoot factor; 1.0 means "just
    # at the rule threshold", 2.0 means "2x past it". Saturates at 2x —
    # any pattern that doubles its rule threshold is treated as a fully
    # velocity-driven signal.
    return _clamp(trigger_margin / 2.0)


def _narrative_subscore(bucket_count_window: int, trigger_margin: float) -> float:
    # A bucket that fired a rule already evidences a coherent narrative
    # cluster (0.70 baseline). Each unit of overshoot adds 0.30, so a
    # 2x-past-threshold bucket saturates the channel.
    if bucket_count_window == 0 or trigger_margin == 0:
        return 0.0
    return _clamp(0.70 + (trigger_margin - 1.0) * 0.30)


def _sentiment_subscore_proxy(trigger_margin: float) -> float:
    # No live sentiment model — flagged in ``proxy_channels``. The proxy
    # reads the same trigger_margin signal: a stronger pattern is treated
    # as evidence of heavier sentiment burden. Floor 0.60 so marginal
    # patterns never go below MEDIUM-band territory.
    return _clamp(0.60 + 0.40 * (trigger_margin / 2.0))


def _market_subscore_proxy(trigger_margin: float) -> float:
    # No live peer-benchmark model — flagged in ``proxy_channels``. Same
    # proxy shape as sentiment.
    return _clamp(0.60 + 0.40 * (trigger_margin / 2.0))


def score_severity(inputs: SeverityInputs) -> SeverityResult:
    """Compute the composite severity for one detected pattern.

    Uses the locked weights from :data:`LOCKED_WEIGHTS`. The result
    carries every intermediate value so the audit chain can replay the
    decision deterministically.
    """
    sub_scores = {
        "indecopi": _indecopi_subscore(inputs.indecopi_case_count),
        "sentiment": _sentiment_subscore_proxy(inputs.trigger_margin),
        "narrative": _narrative_subscore(
            inputs.bucket_count_window, inputs.trigger_margin
        ),
        "velocity": _velocity_subscore(inputs.trigger_margin),
        "market": _market_subscore_proxy(inputs.trigger_margin),
    }
    contributions = {
        channel: round(sub_scores[channel] * weight, 4)
        for channel, weight in LOCKED_WEIGHTS.items()
    }
    score = round(sum(contributions.values()), 4)
    return SeverityResult(
        score=score,
        band=_band(score),
        sub_scores={k: round(v, 4) for k, v in sub_scores.items()},
        contributions=contributions,
        weights=dict(LOCKED_WEIGHTS),
        inputs={
            "bucket_count_window": float(inputs.bucket_count_window),
            "indecopi_case_count": float(inputs.indecopi_case_count),
            "trigger_margin": round(inputs.trigger_margin, 4),
            "prior_baseline": round(inputs.prior_baseline, 4),
        },
        proxy_channels=("sentiment", "market"),
    )


# ---------------------------------------------------------------------------
# FRAUD_EMERGENCE composite — a SECOND locked weight set (P-RESHAPE-6)
# ---------------------------------------------------------------------------
#
# Fraud-emergence patterns weight social signal and cross-source
# corroboration MORE than the standard composite, and de-emphasise the
# sentiment/market proxies. These weights are LOCKED and DISTINCT from
# LOCKED_WEIGHTS above. The standard set is unchanged for VOLUME_SPIKE,
# SUSTAINED_ELEVATION, CROSS_SOURCE_CORRELATION, NEW_TOPIC_EMERGENCE;
# only FRAUD_EMERGENCE uses the set below.
FRAUD_WEIGHTS: dict[str, float] = {
    "social": 0.30,
    "complaints": 0.25,
    "indecopi": 0.20,
    "velocity": 0.15,
    "market": 0.10,
}


@dataclass(frozen=True)
class FraudSeverityInputs:
    """Inputs for the FRAUD_EMERGENCE composite.

    Counts are window-scoped: social signals in 72h, fraud-category
    complaints in 24h, INDECOPI fraud cases in 7d. ``trigger_margin`` is
    how strongly the social-signal floor (>=5 in 72h) was overshot.
    """

    social_signal_count_72h: int
    fraud_complaint_count_24h: int
    indecopi_fraud_count_7d: int
    trigger_margin: float

    def __post_init__(self) -> None:
        for v in (
            self.social_signal_count_72h,
            self.fraud_complaint_count_24h,
            self.indecopi_fraud_count_7d,
        ):
            if v < 0:
                raise ValueError("fraud severity counts must be non-negative")
        if self.trigger_margin < 0:
            raise ValueError("trigger_margin must be non-negative")


def _social_subscore(count_72h: int) -> float:
    # Saturates at 10 social signals in 72h.
    return _clamp(count_72h / 10.0)


def _complaints_subscore(count_24h: int) -> float:
    # Saturates at 8 fraud-category complaints in 24h.
    return _clamp(count_24h / 8.0)


def score_fraud_severity(inputs: FraudSeverityInputs) -> SeverityResult:
    """Compute the FRAUD_EMERGENCE composite using :data:`FRAUD_WEIGHTS`.

    Returns a :class:`SeverityResult` with the same shape as the standard
    scorer so persistence + the cockpit explanation panel are uniform —
    only the channel set + weights differ. The proxy channel here is
    ``market`` only (social / complaints / indecopi are all real counts;
    velocity derives from the trigger margin)."""
    sub_scores = {
        "social": _social_subscore(inputs.social_signal_count_72h),
        "complaints": _complaints_subscore(inputs.fraud_complaint_count_24h),
        "indecopi": _indecopi_subscore(inputs.indecopi_fraud_count_7d),
        "velocity": _velocity_subscore(inputs.trigger_margin),
        "market": _market_subscore_proxy(inputs.trigger_margin),
    }
    contributions = {
        channel: round(sub_scores[channel] * weight, 4)
        for channel, weight in FRAUD_WEIGHTS.items()
    }
    score = round(sum(contributions.values()), 4)
    return SeverityResult(
        score=score,
        band=_band(score),
        sub_scores={k: round(v, 4) for k, v in sub_scores.items()},
        contributions=contributions,
        weights=dict(FRAUD_WEIGHTS),
        inputs={
            "social_signal_count_72h": float(inputs.social_signal_count_72h),
            "fraud_complaint_count_24h": float(inputs.fraud_complaint_count_24h),
            "indecopi_fraud_count_7d": float(inputs.indecopi_fraud_count_7d),
            "trigger_margin": round(inputs.trigger_margin, 4),
        },
        proxy_channels=("market",),
    )


def score_severity_from_mapping(payload: Mapping[str, Any]) -> SeverityResult:
    """Convenience wrapper for callers holding a dict (e.g. test seeds)."""
    return score_severity(
        SeverityInputs(
            bucket_count_window=int(payload["bucket_count_window"]),
            indecopi_case_count=int(payload.get("indecopi_case_count") or 0),
            trigger_margin=float(payload["trigger_margin"]),
            prior_baseline=float(payload.get("prior_baseline") or 0.0),
        )
    )
