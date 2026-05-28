"""Severity composite scorer — locked weights + band boundaries.

The five channel weights are locked at the sprint level (mirror of
``sbs_api.agents.tools.anomaly.WEIGHTS``). These tests pin the locked
values, the band thresholds (HIGH ≥ 0.70, MEDIUM ≥ 0.40), and the
proxy-channel disclosure on the breakdown payload.
"""

from __future__ import annotations

import pytest

from sbs_api.aggregation.severity import (
    HIGH_THRESHOLD,
    LOCKED_WEIGHTS,
    MEDIUM_THRESHOLD,
    SeverityBand,
    SeverityInputs,
    score_severity,
)


def test_locked_weights_sum_to_one():
    assert sum(LOCKED_WEIGHTS.values()) == pytest.approx(1.0)


def test_locked_weights_are_pinned_per_channel():
    assert LOCKED_WEIGHTS == {
        "indecopi": 0.30,
        "sentiment": 0.20,
        "narrative": 0.25,
        "velocity": 0.15,
        "market": 0.10,
    }


def test_band_thresholds_pinned():
    assert HIGH_THRESHOLD == 0.70
    assert MEDIUM_THRESHOLD == 0.40


def test_zero_inputs_score_low_band_from_proxy_floor_only():
    """All data channels at zero — only the sentiment/market proxy
    floors (0.6 * 0.20 + 0.6 * 0.10 = 0.18) contribute. Well under
    MEDIUM."""
    result = score_severity(
        SeverityInputs(
            bucket_count_window=0,
            indecopi_case_count=0,
            trigger_margin=0.0,
            prior_baseline=0.0,
        )
    )
    assert result.band == SeverityBand.LOW
    assert result.score < MEDIUM_THRESHOLD


def test_marginal_pattern_lands_medium():
    """Just-at-threshold pattern (margin == 1.0) with no indecopi must
    land in MEDIUM, not HIGH — only stronger signals justify pulling a
    supervisor."""
    result = score_severity(
        SeverityInputs(
            bucket_count_window=3,
            indecopi_case_count=0,
            trigger_margin=1.0,
            prior_baseline=1.2,
        )
    )
    assert result.band == SeverityBand.MEDIUM


def test_volume_spike_8_vs_1_no_indecopi_is_high():
    """The P-RESHAPE-2 demo seed (8 in 24h vs 1.0 daily baseline) must
    cross the HIGH threshold exactly. Without INDECOPI corroboration
    the math sits at the locked 0.70 boundary by design."""
    margin = (8 / 1.0) / 2.5  # = 3.2
    result = score_severity(
        SeverityInputs(
            bucket_count_window=8,
            indecopi_case_count=0,
            trigger_margin=margin,
            prior_baseline=1.0,
        )
    )
    assert result.band == SeverityBand.HIGH
    assert result.score >= HIGH_THRESHOLD


def test_cross_source_with_indecopi_lands_high_comfortably():
    """The CROSS_SOURCE_CORRELATION seed (12 vs 6 complaints, 4 vs 2
    INDECOPI) should land HIGH with room to spare — the corroborating
    INDECOPI signal alone weighs 0.30 of the composite."""
    complaints_margin = (12 / 6) / 1.5  # = 1.333
    indecopi_margin = (4 / 2) / 1.3  # = 1.538
    margin = min(complaints_margin, indecopi_margin)
    result = score_severity(
        SeverityInputs(
            bucket_count_window=12,
            indecopi_case_count=4,
            trigger_margin=margin,
            prior_baseline=6.0,
        )
    )
    assert result.band == SeverityBand.HIGH
    assert result.score >= 0.75


def test_breakdown_carries_locked_weights_subscores_and_proxy_disclosure():
    result = score_severity(
        SeverityInputs(
            bucket_count_window=8,
            indecopi_case_count=2,
            trigger_margin=2.0,
            prior_baseline=1.0,
        )
    )
    payload = result.to_breakdown()
    assert payload["weights"] == LOCKED_WEIGHTS
    assert set(payload["sub_scores"]) == set(LOCKED_WEIGHTS)
    assert set(payload["contributions"]) == set(LOCKED_WEIGHTS)
    # Every contribution = sub_score * locked weight (no hidden modifier).
    for channel, weight in LOCKED_WEIGHTS.items():
        assert payload["contributions"][channel] == pytest.approx(
            payload["sub_scores"][channel] * weight, abs=1e-3
        )
    # Proxy channels are disclosed so the cockpit can render them as such.
    assert "sentiment" in payload["proxy_channels"]
    assert "market" in payload["proxy_channels"]


def test_indecopi_subscore_saturates_at_five_cases():
    no_indecopi = score_severity(
        SeverityInputs(
            bucket_count_window=10,
            indecopi_case_count=0,
            trigger_margin=2.0,
            prior_baseline=1.0,
        )
    )
    saturated = score_severity(
        SeverityInputs(
            bucket_count_window=10,
            indecopi_case_count=5,
            trigger_margin=2.0,
            prior_baseline=1.0,
        )
    )
    over_saturated = score_severity(
        SeverityInputs(
            bucket_count_window=10,
            indecopi_case_count=42,
            trigger_margin=2.0,
            prior_baseline=1.0,
        )
    )
    assert saturated.score > no_indecopi.score
    assert saturated.sub_scores["indecopi"] == pytest.approx(1.0)
    assert over_saturated.sub_scores["indecopi"] == pytest.approx(1.0)
    assert over_saturated.score == saturated.score


def test_negative_inputs_rejected():
    with pytest.raises(ValueError):
        SeverityInputs(
            bucket_count_window=-1,
            indecopi_case_count=0,
            trigger_margin=1.0,
            prior_baseline=0.0,
        )
    with pytest.raises(ValueError):
        SeverityInputs(
            bucket_count_window=1,
            indecopi_case_count=-2,
            trigger_margin=1.0,
            prior_baseline=0.0,
        )
    with pytest.raises(ValueError):
        SeverityInputs(
            bucket_count_window=1,
            indecopi_case_count=0,
            trigger_margin=-0.1,
            prior_baseline=0.0,
        )
