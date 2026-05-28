"""Percentile-core tests — exercise the numpy helpers directly.

``compute_peer_percentile`` needs a DB session (covered in
test_pattern_to_peer_risk + test_peer_risk_radar). The positioning
math (``_percentile_of``, ``_z_score``) is pure and tested here.
"""

from __future__ import annotations

import pytest

from sbs_api.peer_risk import percentiles as pc


def test_percentile_of_max_value_is_high():
    # 8 against peers all at 2 → top of the distribution.
    dist = [2, 2, 2, 2, 8]
    p = pc._percentile_of(8, dist)
    assert p is not None
    assert p >= 90.0


def test_percentile_of_median_value():
    dist = [1, 2, 3, 4, 5]
    p = pc._percentile_of(3, dist)
    # 3 is the middle of 5 → around 50th percentile.
    assert 40.0 <= p <= 60.0


def test_percentile_of_empty_distribution_is_none():
    assert pc._percentile_of(5, []) is None


def test_z_score_outlier():
    dist = [2, 2, 2, 2, 8]
    z = pc._z_score(8, dist)
    assert z is not None
    assert z >= 2.0


def test_z_score_zero_variance_is_none():
    assert pc._z_score(5, [5, 5, 5, 5]) is None


def test_z_score_empty_is_none():
    assert pc._z_score(5, []) is None
