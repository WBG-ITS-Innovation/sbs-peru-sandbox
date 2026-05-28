"""Pattern detector — one positive + one negative case per rule.

The detector is a pure function over :class:`BucketWindow`. These
tests construct buckets directly so no Postgres is required.

Rule contract (locked, P-RESHAPE-2):

* VOLUME_SPIKE — count_24h ≥ 3 AND count_24h ≥ 2.5 * prior_7d_mean
  AND prior_7d_mean ≥ 1.0
* SUSTAINED_ELEVATION — count_7d ≥ 1.8 * prior_4w_weekly_mean AND
  prior_4w_weekly_mean ≥ 5.0
* CROSS_SOURCE_CORRELATION — complaints WoW ≥ 1.5 AND INDECOPI WoW ≥ 1.3
* NEW_TOPIC_EMERGENCE — count_24h ≥ 5 AND count_30d_prior == 0 AND
  no activity in [now-30d, now-24h]
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sbs_api.aggregation.detector import (
    PatternType,
    detect_patterns,
)
from sbs_api.aggregation.windower import BucketWindow

NOW = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)


def _bucket(**overrides) -> BucketWindow:
    """A 'cold' bucket — every count zero — that the per-rule tests
    selectively warm up. Avoids accidentally satisfying a sibling rule
    while testing a specific one."""
    defaults: dict[str, object] = {
        "institution_id": "SBS-001234",
        "complaint_category": "COBRO_INDEBIDO",
        "now": NOW,
        "count_24h": 0,
        "count_7d": 0,
        "count_30d": 0,
        "count_30d_prior": 0,
        "prior_7d_daily_mean": 0.0,
        "prior_4w_weekly_mean": 0.0,
        "complaints_7d_prior": 0,
        "indecopi_count_7d": 0,
        "indecopi_count_7d_prior": 0,
        "contributing_complaint_ids_24h": tuple(),
        "contributing_complaint_ids_7d": tuple(),
        "contributing_indecopi_case_ids_7d": tuple(),
    }
    defaults.update(overrides)
    return BucketWindow(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# VOLUME_SPIKE
# ---------------------------------------------------------------------------


def test_volume_spike_fires_when_ratio_and_floor_met():
    bucket = _bucket(
        count_24h=8,
        prior_7d_daily_mean=1.0,
        contributing_complaint_ids_24h=tuple(f"BCO-2026-{i:06d}" for i in range(1, 9)),
    )
    candidates = detect_patterns([bucket])
    types = [c.pattern_type for c in candidates]
    assert PatternType.VOLUME_SPIKE in types
    spike = next(c for c in candidates if c.pattern_type == PatternType.VOLUME_SPIKE)
    assert spike.bucket_count_window == 8
    assert spike.trigger_margin == pytest.approx(8 / 1.0 / 2.5)
    assert spike.contributing_complaint_ids == bucket.contributing_complaint_ids_24h


def test_volume_spike_does_not_fire_when_prior_mean_below_floor():
    """Same ratio, prior mean below 1.0 — the floor exists to prevent
    'doubled from 0.1 to 0.3' noise from paging the supervisor."""
    bucket = _bucket(count_24h=3, prior_7d_daily_mean=0.5)
    candidates = detect_patterns([bucket])
    assert PatternType.VOLUME_SPIKE not in [c.pattern_type for c in candidates]


# ---------------------------------------------------------------------------
# SUSTAINED_ELEVATION
# ---------------------------------------------------------------------------


def test_sustained_elevation_fires_when_ratio_and_floor_met():
    bucket = _bucket(count_7d=20, prior_4w_weekly_mean=10.0)
    candidates = detect_patterns([bucket])
    assert PatternType.SUSTAINED_ELEVATION in [c.pattern_type for c in candidates]


def test_sustained_elevation_blocked_by_prior_mean_floor():
    bucket = _bucket(count_7d=20, prior_4w_weekly_mean=4.0)
    candidates = detect_patterns([bucket])
    assert PatternType.SUSTAINED_ELEVATION not in [c.pattern_type for c in candidates]


# ---------------------------------------------------------------------------
# CROSS_SOURCE_CORRELATION
# ---------------------------------------------------------------------------


def test_cross_source_fires_when_both_ratios_met():
    bucket = _bucket(
        count_7d=12,
        complaints_7d_prior=6,
        indecopi_count_7d=4,
        indecopi_count_7d_prior=2,
        contributing_complaint_ids_7d=tuple(f"COP-2026-{i:06d}" for i in range(1, 13)),
        contributing_indecopi_case_ids_7d=("IND-1", "IND-2", "IND-3", "IND-4"),
    )
    candidates = detect_patterns([bucket])
    cross = next(
        (c for c in candidates if c.pattern_type == PatternType.CROSS_SOURCE_CORRELATION),
        None,
    )
    assert cross is not None
    assert cross.indecopi_case_count == 4
    assert cross.contributing_indecopi_case_ids == bucket.contributing_indecopi_case_ids_7d


def test_cross_source_blocked_when_indecopi_ratio_below_threshold():
    """Complaints up 100% but INDECOPI only up 20% — fails the
    cross-source rule's INDECOPI ratio floor (1.3x)."""
    bucket = _bucket(
        count_7d=12,
        complaints_7d_prior=6,
        indecopi_count_7d=6,
        indecopi_count_7d_prior=5,
    )
    candidates = detect_patterns([bucket])
    assert PatternType.CROSS_SOURCE_CORRELATION not in [
        c.pattern_type for c in candidates
    ]


# ---------------------------------------------------------------------------
# NEW_TOPIC_EMERGENCE
# ---------------------------------------------------------------------------


def test_new_topic_fires_for_clean_30d_history():
    bucket = _bucket(
        count_24h=6,
        count_7d=6,
        count_30d=6,
        count_30d_prior=0,
        contributing_complaint_ids_24h=tuple(
            f"NEW-2026-{i:06d}" for i in range(1, 7)
        ),
    )
    candidates = detect_patterns([bucket])
    assert PatternType.NEW_TOPIC_EMERGENCE in [c.pattern_type for c in candidates]


def test_new_topic_blocked_when_30d_prior_had_activity():
    """Even with a 24h surge, if the category was active in the prior
    30-day window it is not a new topic."""
    bucket = _bucket(
        count_24h=6,
        count_7d=6,
        count_30d=6,
        count_30d_prior=4,
    )
    candidates = detect_patterns([bucket])
    assert PatternType.NEW_TOPIC_EMERGENCE not in [c.pattern_type for c in candidates]


def test_new_topic_blocked_when_recent_30d_window_had_activity():
    """30d window has more entries than 24h window — activity in the
    [now-30d, now-24h] band — so the topic is not new even with a
    clean 30d-prior window."""
    bucket = _bucket(
        count_24h=6,
        count_30d=10,
        count_30d_prior=0,
    )
    candidates = detect_patterns([bucket])
    assert PatternType.NEW_TOPIC_EMERGENCE not in [c.pattern_type for c in candidates]


# ---------------------------------------------------------------------------
# Determinism — buckets listed back in (institution, category) order
# ---------------------------------------------------------------------------


def test_detector_output_is_deterministic_across_runs():
    bucket_a = _bucket(
        institution_id="SBS-001234",
        complaint_category="COBRO_INDEBIDO",
        count_24h=8,
        prior_7d_daily_mean=1.0,
    )
    bucket_b = _bucket(
        institution_id="SBS-005678",
        complaint_category="DEMORA_ATENCION",
        count_24h=6,
        prior_7d_daily_mean=1.0,
    )
    first = [(c.institution_id, c.pattern_type) for c in detect_patterns([bucket_b, bucket_a])]
    second = [(c.institution_id, c.pattern_type) for c in detect_patterns([bucket_a, bucket_b])]
    assert first == second
