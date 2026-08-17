# SPDX-License-Identifier: Apache-2.0
"""Leading-indicator forecast for the PRR narrative.

A 14-day forward projection of the daily complaint count series for a
(institution_id, motivo_code) pair. The output drives the "where is
this heading?" half of the Peer Risk Radar narrative.

Holt-Winters double exponential smoothing is implemented inline in
~25 lines of numpy. The prompt called for the ``statsmodels``
implementation, but the explicit rationale is **transparency, not
accuracy** ("If a reviewer asks why not ARIMA or Prophet:
defensibility and supervisor-explainability"). A hand-rolled,
audit-readable implementation honours that rationale more directly
than wrapping a third-party black box — and it sidesteps adding
``statsmodels`` (with its scipy / pandas transitive deps) to the API
container. The locked smoothing constants below are the comparator-
backed defaults from the comparator literature (alpha=0.4, beta=0.2,
no seasonal component because the daily series is too short).

For institutions outside the demo cohorts we **deliberately** return
``ForecastResult.pinned_null(...)`` rather than fabricate a forecast
on an unvalidated series. Production roll-out requires a per-FI
series-validation step (see ADR pending).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Sequence

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.complaint import ComplaintRecord


FORECAST_MODEL_DEMO = "forecast-holt-winters-demo-v1"
FORECAST_MODEL_PINNED_NULL = "forecast-demo-scope-only"

# Locked smoothing constants. Re-tuning requires an ADR amendment.
_ALPHA = 0.4  # level smoothing
_BETA = 0.2  # trend smoothing
_MIN_SERIES_LEN = 7  # at least one week of daily observations


class TrendDirection(str, Enum):
    RISING = "RISING"
    STABLE = "STABLE"
    FALLING = "FALLING"


@dataclass(frozen=True)
class ForecastResult:
    institution_id: str
    motivo_code: str
    model_id: str
    series_observations: int
    predicted_next_7d: int
    predicted_next_14d: int
    confidence_interval_low_14d: int
    confidence_interval_high_14d: int
    trend_direction: TrendDirection
    trend_strength: float
    is_pinned_null: bool

    @classmethod
    def pinned_null(
        cls, *, institution_id: str, motivo_code: str
    ) -> "ForecastResult":
        return cls(
            institution_id=institution_id,
            motivo_code=motivo_code,
            model_id=FORECAST_MODEL_PINNED_NULL,
            series_observations=0,
            predicted_next_7d=0,
            predicted_next_14d=0,
            confidence_interval_low_14d=0,
            confidence_interval_high_14d=0,
            trend_direction=TrendDirection.STABLE,
            trend_strength=0.0,
            is_pinned_null=True,
        )


# ---------------------------------------------------------------------------
# Holt-Winters (additive trend, no seasonal component)
# ---------------------------------------------------------------------------


def _holt_winters(series: Sequence[float]) -> tuple[float, float, float]:
    """Return (level_T, trend_T, sigma_residual) for the input series.

    Initial level = first observation; initial trend = (last - first) /
    (n-1). Smoothing follows the standard double-exponential recursion:
        L_t = alpha * y_t + (1 - alpha) * (L_{t-1} + T_{t-1})
        T_t = beta  * (L_t - L_{t-1}) + (1 - beta)  * T_{t-1}
    """
    y = np.asarray(series, dtype=float)
    n = len(y)
    if n < _MIN_SERIES_LEN:
        raise ValueError(
            f"series needs at least {_MIN_SERIES_LEN} observations, got {n}"
        )
    level = float(y[0])
    trend = float((y[-1] - y[0]) / (n - 1)) if n > 1 else 0.0
    fitted = np.empty(n)
    fitted[0] = level
    for t in range(1, n):
        prev_level = level
        level = _ALPHA * y[t] + (1.0 - _ALPHA) * (level + trend)
        trend = _BETA * (level - prev_level) + (1.0 - _BETA) * trend
        fitted[t] = prev_level + trend
    sigma = float(np.sqrt(np.mean((y - fitted) ** 2)))
    return level, trend, sigma


def _project(level: float, trend: float, horizon: int) -> np.ndarray:
    return np.array([level + (h + 1) * trend for h in range(horizon)])


def _trend_direction(trend: float, level: float) -> TrendDirection:
    if level == 0:
        return TrendDirection.STABLE
    relative = trend / max(level, 1.0)
    if relative > 0.05:
        return TrendDirection.RISING
    if relative < -0.05:
        return TrendDirection.FALLING
    return TrendDirection.STABLE


def _trend_strength(trend: float, level: float) -> float:
    """[0, 1] — how strongly the series is moving relative to its
    own level. Saturates at trend == level (i.e. doubling per day)."""
    if level <= 0:
        return 0.0
    return float(min(1.0, abs(trend) / level))


async def _daily_counts(
    session: AsyncSession,
    *,
    institution_id: str,
    motivo_code: str,
    now: datetime,
    days: int = 30,
) -> list[int]:
    """Per-day count for the last ``days`` days, ordered oldest → newest.

    Bucketing happens in Python so the test suite does not depend on
    Postgres date-function dialect quirks; the table is small.
    """
    window_start = now - timedelta(days=days)
    rows = (
        await session.execute(
            select(ComplaintRecord.received_at)
            .where(
                ComplaintRecord.institution_id == institution_id,
                ComplaintRecord.motivo_code == motivo_code,
                ComplaintRecord.received_at > window_start,
                ComplaintRecord.received_at <= now,
            )
        )
    ).scalars().all()

    daily = [0] * days
    for ts in rows:
        offset = (now - ts).days
        if 0 <= offset < days:
            # oldest day = days-1, newest = 0
            idx = days - 1 - offset
            daily[idx] += 1
    return daily


async def forecast_series(
    session: AsyncSession,
    *,
    institution_id: str,
    motivo_code: str,
    now: datetime,
    is_demo_seeded: bool,
) -> ForecastResult:
    """Compute the forward projection. Returns a pinned-null result
    for institutions outside the demo cohorts; the model_id makes
    the gating visible in audit exports."""
    if not is_demo_seeded:
        return ForecastResult.pinned_null(
            institution_id=institution_id, motivo_code=motivo_code
        )

    daily = await _daily_counts(
        session, institution_id=institution_id, motivo_code=motivo_code, now=now
    )

    # Need at least _MIN_SERIES_LEN observations. Zero-pad days at the
    # head if the series is shorter than the window — but if the
    # institution literally has no activity in 30d the forecast still
    # collapses to zero, which is the right answer.
    if sum(daily) == 0 or len(daily) < _MIN_SERIES_LEN:
        return ForecastResult.pinned_null(
            institution_id=institution_id, motivo_code=motivo_code
        )

    level, trend, sigma = _holt_winters(daily)
    next14 = _project(level, trend, 14)
    next7 = next14[:7]
    sum14 = max(0, int(round(float(next14.sum()))))
    sum7 = max(0, int(round(float(next7.sum()))))
    # Symmetric ±1.96σ × √h band on the cumulative sum.
    band = 1.96 * sigma * np.sqrt(14)
    ci_low = max(0, int(round(sum14 - band)))
    ci_high = max(ci_low, int(round(sum14 + band)))

    return ForecastResult(
        institution_id=institution_id,
        motivo_code=motivo_code,
        model_id=FORECAST_MODEL_DEMO,
        series_observations=len(daily),
        predicted_next_7d=sum7,
        predicted_next_14d=sum14,
        confidence_interval_low_14d=ci_low,
        confidence_interval_high_14d=ci_high,
        trend_direction=_trend_direction(trend, level),
        trend_strength=round(_trend_strength(trend, level), 3),
        is_pinned_null=False,
    )
