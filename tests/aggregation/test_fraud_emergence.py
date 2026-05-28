"""FRAUD_EMERGENCE detection + locked fraud-weight severity (P-RESHAPE-6)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sbs_api.aggregation.detector import (
    PatternType,
    detect_fraud_emergence,
)
from sbs_api.aggregation.severity import (
    FRAUD_WEIGHTS,
    LOCKED_WEIGHTS,
    FraudSeverityInputs,
    SeverityBand,
    score_fraud_severity,
)
from sbs_api.aggregation.windower import FraudWindow

NOW = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)


def _fw(**kw) -> FraudWindow:
    defaults = dict(
        institution_id="SBS-001234",
        now=NOW,
        social_signal_count_72h=0,
        fraud_complaint_count_24h=0,
        indecopi_fraud_count_7d=0,
        contributing_complaint_ids_24h=(),
        contributing_social_signal_ids_72h=(),
        contributing_indecopi_case_ids_7d=(),
        detected_fraud_indicators=(),
    )
    defaults.update(kw)
    return FraudWindow(**defaults)  # type: ignore[arg-type]


def test_fraud_weight_set_is_distinct_and_locked():
    assert FRAUD_WEIGHTS == {
        "social": 0.30,
        "complaints": 0.25,
        "indecopi": 0.20,
        "velocity": 0.15,
        "market": 0.10,
    }
    assert FRAUD_WEIGHTS != LOCKED_WEIGHTS
    assert round(sum(FRAUD_WEIGHTS.values()), 4) == 1.0


def test_fires_with_social_plus_complaint_arm():
    cands = detect_fraud_emergence(
        [_fw(social_signal_count_72h=14, fraud_complaint_count_24h=4)]
    )
    assert len(cands) == 1
    assert cands[0].institution_id == "SBS-001234"


def test_fires_with_social_plus_indecopi_arm():
    cands = detect_fraud_emergence(
        [_fw(social_signal_count_72h=6, indecopi_fraud_count_7d=2)]
    )
    assert len(cands) == 1


def test_does_not_fire_without_social_floor():
    # Only 4 social signals (< 5) — no fire even with complaints.
    cands = detect_fraud_emergence(
        [_fw(social_signal_count_72h=4, fraud_complaint_count_24h=10)]
    )
    assert cands == []


def test_does_not_fire_with_social_only():
    # Social floor met but neither complaint nor indecopi arm.
    cands = detect_fraud_emergence(
        [_fw(social_signal_count_72h=8, fraud_complaint_count_24h=1, indecopi_fraud_count_7d=1)]
    )
    assert cands == []


def test_seed_shape_scores_high_with_fraud_weights():
    margin = 14 / 5
    result = score_fraud_severity(
        FraudSeverityInputs(
            social_signal_count_72h=14,
            fraud_complaint_count_24h=4,
            indecopi_fraud_count_7d=3,
            trigger_margin=margin,
        )
    )
    assert result.band == SeverityBand.HIGH
    assert result.weights == FRAUD_WEIGHTS
    # Social is the heaviest channel in the fraud set.
    assert set(result.sub_scores) == set(FRAUD_WEIGHTS)


def test_pattern_type_enum_has_fraud_emergence():
    assert PatternType.FRAUD_EMERGENCE.value == "FRAUD_EMERGENCE"
