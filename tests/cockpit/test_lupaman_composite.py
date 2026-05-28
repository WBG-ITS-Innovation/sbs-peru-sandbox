"""Lupaman composite — PRR + Sector Broadcast aggregated for display (P-RESHAPE-8.5).

Lupaman is UX-only: its card aggregates two separate underlying agents.
Their rows stay distinct (each recent_run is labelled with its underlying
agent_id), but counts/latency are merged.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.cockpit.conftest import hdr, seed_agent_runs
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


@pytest.mark.asyncio
async def test_lupaman_total_equals_sum_of_underlying(secret_app, test_database_url):
    await seed_agent_runs(
        test_database_url,
        [
            {"agent_name": "peer-risk-radar", "status": "success", "started_minutes_ago": 20},
            {"agent_name": "peer-risk-radar", "status": "success", "started_minutes_ago": 40},
            {"agent_name": "peer-risk-radar", "status": "partial", "started_minutes_ago": 60},
            {"agent_name": "sector-broadcast", "status": "success", "started_minutes_ago": 30},
            {"agent_name": "sector-broadcast", "status": "failed", "started_minutes_ago": 50},
        ],
    )
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/v1/internal/cockpit/agents", headers=hdr("sbs:conduct:head"))
    assert r.status_code == 200
    lupaman = next(a for a in r.json()["agents"] if a["agent_id"] == "lupaman")
    # 3 PRR + 2 Sector Broadcast = 5.
    assert lupaman["total_runs_in_window"] == 5
    # recent_runs preserve each underlying agent's provenance.
    underlying = {run["underlying_agent_id"] for run in lupaman["recent_runs"]}
    assert underlying == {"peer-risk-radar", "sector-broadcast"}


@pytest.mark.asyncio
async def test_lupaman_runs_endpoint_merges_both(secret_app, test_database_url):
    await seed_agent_runs(
        test_database_url,
        [
            {"agent_name": "peer-risk-radar", "status": "success", "started_minutes_ago": 20},
            {"agent_name": "sector-broadcast", "status": "success", "started_minutes_ago": 30},
        ],
    )
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(
            "/v1/internal/cockpit/agents/lupaman/runs", headers=hdr("sbs:conduct:head")
        )
    assert r.status_code == 200
    assert r.json()["count"] == 2
