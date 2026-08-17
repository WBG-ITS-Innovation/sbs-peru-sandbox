# SPDX-License-Identifier: Apache-2.0
"""Forecast tests — exercise the Holt-Winters numpy core directly.

``forecast_series`` needs a DB session, but the math underneath
(``_holt_winters``, ``_project``, trend classification) is pure and
can be tested without Postgres. The DB-integration path is covered in
test_pattern_to_peer_risk.
"""

from __future__ import annotations

import numpy as np
import pytest

from sbs_api.peer_risk import forecast as fc


def test_holt_winters_recovers_linear_trend():
    # Perfectly linear rising series → trend ≈ slope, projection rises.
    series = [float(i) for i in range(1, 15)]  # 1..14
    level, trend, sigma = fc._holt_winters(series)
    assert trend > 0
    proj = fc._project(level, trend, 14)
    assert proj[-1] > proj[0]
    assert sigma == pytest.approx(0.0, abs=0.5)


def test_holt_winters_flat_series_has_near_zero_trend():
    series = [5.0] * 14
    level, trend, sigma = fc._holt_winters(series)
    assert abs(trend) < 0.01
    assert fc._trend_direction(trend, level) == fc.TrendDirection.STABLE


def test_holt_winters_rejects_short_series():
    with pytest.raises(ValueError):
        fc._holt_winters([1.0, 2.0, 3.0])


def test_trend_direction_thresholds():
    assert fc._trend_direction(1.0, 10.0) == fc.TrendDirection.RISING
    assert fc._trend_direction(-1.0, 10.0) == fc.TrendDirection.FALLING
    assert fc._trend_direction(0.1, 100.0) == fc.TrendDirection.STABLE


def test_trend_strength_saturates_at_one():
    assert fc._trend_strength(50.0, 10.0) == 1.0
    assert fc._trend_strength(0.0, 10.0) == 0.0
    assert 0.0 < fc._trend_strength(2.0, 10.0) < 1.0


def test_pinned_null_result_shape():
    r = fc.ForecastResult.pinned_null(institution_id="SBS-9999", motivo_code="OTRO")
    assert r.is_pinned_null is True
    assert r.model_id == fc.FORECAST_MODEL_PINNED_NULL
    assert r.predicted_next_7d == 0
    assert r.trend_direction == fc.TrendDirection.STABLE
