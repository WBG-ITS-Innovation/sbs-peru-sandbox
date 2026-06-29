# SPDX-License-Identifier: Apache-2.0
"""Peer-comparison building blocks.

Three deterministic helpers — cohort assignment, peer-percentile
computation, and leading-indicator forecast — used by the conduct
cockpit's aggregates route to position one institution against its
peer cohort.

The helpers are pure compute (no model provider), so they are
unit-testable on their own.
"""

from sbs_api.peer_risk.cohorts import (
    Cohort,
    CohortAssignmentError,
    InstitutionSegment,
    SizeTier,
    assign_cohort,
)
from sbs_api.peer_risk.forecast import (
    FORECAST_MODEL_DEMO,
    FORECAST_MODEL_PINNED_NULL,
    ForecastResult,
    TrendDirection,
    forecast_series,
)
from sbs_api.peer_risk.percentiles import (
    PercentileResult,
    compute_peer_percentile,
)

__all__ = [
    "Cohort",
    "CohortAssignmentError",
    "FORECAST_MODEL_DEMO",
    "FORECAST_MODEL_PINNED_NULL",
    "ForecastResult",
    "InstitutionSegment",
    "PercentileResult",
    "SizeTier",
    "TrendDirection",
    "assign_cohort",
    "compute_peer_percentile",
    "forecast_series",
]
