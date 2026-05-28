"""Unified agent monitoring — list shape + status boundaries (P-RESHAPE-8.5)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from sbs_api.agents.registry import AGENT_REGISTRY
from sbs_api.agents.status import compute_status
from sbs_api.db.models.agent_run import AgentRun
from tests.cockpit.conftest import hdr, seed_agent_runs
from tests.conftest import pytestmark_db

NOW = datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc)


def _run(status: str, *, mins_ago: int, dur_ms: int = 200) -> AgentRun:
    started = NOW - timedelta(minutes=mins_ago)
    ended = None if status == "in_progress" else started + timedelta(milliseconds=dur_ms)
    return AgentRun(
        id=str(uuid.uuid4()),
        complaint_id="BCO-2026-000001",
        agent_name="triage",
        agent_version="triage-0.1.0",
        started_at=started,
        ended_at=ended,
        status=status,
        tool_calls=[],
        final_output=None,
        error=None,
    )


# --- Pure status boundary tests (no DB) -----------------------------------


def test_status_idle_when_all_healthy_and_old():
    runs = [_run("success", mins_ago=60), _run("success", mins_ago=120)]
    assert compute_status(runs, NOW) == "IDLE"


def test_status_running_with_recent_in_progress():
    runs = [_run("success", mins_ago=60), _run("in_progress", mins_ago=1)]
    assert compute_status(runs, NOW) == "RUNNING"


def test_in_progress_older_than_5min_is_not_running():
    # An in-flight row started 10 min ago is stale, not RUNNING.
    runs = [_run("in_progress", mins_ago=10), _run("success", mins_ago=60)]
    assert compute_status(runs, NOW) != "RUNNING"


def test_status_degraded_on_low_success_rate():
    runs = [_run("success", mins_ago=30)] + [
        _run("failed", mins_ago=30) for _ in range(4)
    ]
    assert compute_status(runs, NOW) == "DEGRADED"


def test_status_degraded_on_high_p95_latency():
    runs = [_run("success", mins_ago=30, dur_ms=6000) for _ in range(3)]
    assert compute_status(runs, NOW) == "DEGRADED"


# --- DB-backed list endpoint ----------------------------------------------

pytestmark = pytestmark_db


@pytest.mark.asyncio
async def test_list_returns_all_six_for_unit_head(secret_app, test_database_url):
    await seed_agent_runs(
        test_database_url,
        [
            {"agent_name": "triage", "status": "success", "started_minutes_ago": 30},
            {"agent_name": "triage", "status": "success", "started_minutes_ago": 90},
            {
                "agent_name": "investigation",
                "status": "in_progress",
                "started_minutes_ago": 1,
            },
        ],
    )
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(
            "/v1/internal/cockpit/agents", headers=hdr("sbs:conduct:head")
        )
    assert r.status_code == 200
    body = r.json()
    assert {a["agent_id"] for a in body["agents"]} == set(AGENT_REGISTRY)
    assert body["window"] == "24h"
    triage = next(a for a in body["agents"] if a["agent_id"] == "triage")
    assert triage["total_runs_in_window"] == 2
    assert "recent_runs" in triage
    invest = next(a for a in body["agents"] if a["agent_id"] == "investigation")
    assert invest["status"] == "RUNNING"


@pytest.mark.asyncio
async def test_window_param_narrows_counts(secret_app, test_database_url):
    await seed_agent_runs(
        test_database_url,
        [
            {"agent_name": "triage", "status": "success", "started_minutes_ago": 30},
            # 3 days ago — inside 7d, outside 24h.
            {
                "agent_name": "triage",
                "status": "success",
                "started_minutes_ago": 60 * 24 * 3,
            },
        ],
    )
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        day = await c.get(
            "/v1/internal/cockpit/agents?window=24h", headers=hdr("sbs:conduct:head")
        )
        week = await c.get(
            "/v1/internal/cockpit/agents?window=7d", headers=hdr("sbs:conduct:head")
        )
    d_triage = next(a for a in day.json()["agents"] if a["agent_id"] == "triage")
    w_triage = next(a for a in week.json()["agents"] if a["agent_id"] == "triage")
    assert d_triage["total_runs_in_window"] == 1
    assert w_triage["total_runs_in_window"] == 2
