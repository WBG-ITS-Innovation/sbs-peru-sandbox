"""Agent status + telemetry, computed at query time (P-RESHAPE-8.5).

No status table: an agent's IDLE / RUNNING / DEGRADED state and its
latency/success aggregates are derived from ``agent_runs`` rows.

Status rules (A.6):
* RUNNING  — an in-flight run (status='in_progress') started within the
  last ``RUNNING_WINDOW_MIN`` minutes.
* DEGRADED — over the last ``DEGRADED_WINDOW_HOURS`` hours, success rate
  < ``SUCCESS_FLOOR`` OR p95 latency > ``P95_THRESHOLD_MS``.
* IDLE     — otherwise.

These functions take a flat list of ``AgentRun`` rows so the composite
(Lupaman = peer-risk-radar + sector-broadcast) is handled by merging
both agents' rows before calling in.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from sbs_api.db.models.agent_run import AgentRun

RUNNING_WINDOW_MIN = 5
DEGRADED_WINDOW_HOURS = 24
P95_THRESHOLD_MS = 5000
SUCCESS_FLOOR = 0.80

_TERMINAL = frozenset({"success", "partial", "failed", "timeout"})
_NON_FAILURE = frozenset({"success", "partial"})


def latency_ms(run: AgentRun) -> int | None:
    """Wall-clock duration of a completed run, or None while in flight."""
    if run.started_at is None or run.ended_at is None:
        return None
    return int((run.ended_at - run.started_at).total_seconds() * 1000)


def percentile(values: list[int], p: float) -> int | None:
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, int(p * len(s)))
    return s[idx]


def run_outcome(status: str) -> str:
    """Map an ``agent_runs.status`` to the cockpit recent-run label."""
    if status == "success":
        return "SUCCESS"
    if status == "partial":
        return "FALLBACK"
    if status == "in_progress":
        return "RUNNING"
    return "FAILED"  # failed / timeout


def success_rate(runs: Iterable[AgentRun]) -> float | None:
    """Fraction of terminal runs that produced usable output (success or
    fallback). None when there are no terminal runs."""
    terminal = [r for r in runs if r.status in _TERMINAL]
    if not terminal:
        return None
    good = sum(1 for r in terminal if r.status in _NON_FAILURE)
    return good / len(terminal)


def compute_status(runs: list[AgentRun], now: datetime) -> str:
    """RUNNING / DEGRADED / IDLE for one (possibly composite) agent."""
    running_floor = now - timedelta(minutes=RUNNING_WINDOW_MIN)
    if any(
        r.status == "in_progress" and r.started_at and r.started_at >= running_floor
        for r in runs
    ):
        return "RUNNING"

    window_floor = now - timedelta(hours=DEGRADED_WINDOW_HOURS)
    recent = [r for r in runs if r.started_at and r.started_at >= window_floor]
    rate = success_rate(recent)
    latencies = [latency_ms(r) for r in recent]
    latencies = [v for v in latencies if v is not None]
    p95 = percentile(latencies, 0.95)
    if rate is not None and rate < SUCCESS_FLOOR:
        return "DEGRADED"
    if p95 is not None and p95 > P95_THRESHOLD_MS:
        return "DEGRADED"
    return "IDLE"


def model_id_of(run: AgentRun) -> str | None:
    """Best-effort model id — agents stamp it into ``final_output``."""
    out = run.final_output
    if isinstance(out, dict):
        mid = out.get("model_id")
        if isinstance(mid, str):
            return mid
    return None
