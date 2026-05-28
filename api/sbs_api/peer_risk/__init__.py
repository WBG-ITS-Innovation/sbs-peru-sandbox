"""Peer Risk Radar building blocks.

Three deterministic helpers (cohort assignment, peer-percentile
computation, leading-indicator forecast) feed the Peer Risk Radar
agent's narrative call. The agent itself lives in
``sbs_api.agents.peer_risk_radar``.

Splitting the pure-compute helpers out of the agent keeps the LLM
boundary small (one structured call) and makes the deterministic
checks unit-testable without standing up a model provider.
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
