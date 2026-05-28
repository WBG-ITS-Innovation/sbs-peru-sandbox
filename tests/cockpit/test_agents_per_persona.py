"""Unified agent monitoring — per-persona shaping (P-RESHAPE-8.5).

* Jorge (unit head): all 6, full telemetry.
* Sergio (superintendent): 3 FI-facing cards, NO recent_runs.
* Rosa (SBS IT): all 6 but display branding stripped.
* Per-run detail: Sergio 403, Rosa stripped, conduct full.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from sbs_api.agents.registry import AGENT_REGISTRY, fi_facing_agent_ids
from tests.cockpit.conftest import hdr, seed_agent_runs
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


async def _seed_baseline(test_database_url):
    return await seed_agent_runs(
        test_database_url,
        [
            {
                "agent_name": "triage",
                "status": "success",
                "started_minutes_ago": 30,
                "final_output": {"model_id": "qwen2.5-14b-onprem", "model_provider": "on_prem"},
            },
            {"agent_name": "peer-risk-radar", "status": "success", "started_minutes_ago": 40},
            {"agent_name": "issue-resurface", "status": "success", "started_minutes_ago": 50},
        ],
    )


@pytest.mark.asyncio
async def test_unit_head_sees_six(secret_app, test_database_url):
    await _seed_baseline(test_database_url)
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/v1/internal/cockpit/agents", headers=hdr("sbs:conduct:head"))
    assert r.status_code == 200
    assert len(r.json()["agents"]) == len(AGENT_REGISTRY)


@pytest.mark.asyncio
async def test_superintendent_sees_three_fi_facing_no_recent(
    secret_app, test_database_url
):
    await _seed_baseline(test_database_url)
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(
            "/v1/internal/cockpit/agents", headers=hdr("sbs:superintendent")
        )
    assert r.status_code == 200
    agents = r.json()["agents"]
    assert {a["agent_id"] for a in agents} == set(fi_facing_agent_ids())
    assert len(agents) == 3
    for a in agents:
        assert a["is_fi_facing"] is True
        assert "recent_runs" not in a  # aggregate counts only
        assert "display_name_es" in a  # branding kept for the exec card


@pytest.mark.asyncio
async def test_it_sees_six_without_branding(secret_app, test_database_url):
    await _seed_baseline(test_database_url)
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/v1/internal/cockpit/agents", headers=hdr("sbs:sbs_it"))
    assert r.status_code == 200
    agents = r.json()["agents"]
    assert len(agents) == len(AGENT_REGISTRY)
    for a in agents:
        assert "display_name_es" not in a
        assert "display_name_en" not in a
        assert "character_avatar_id" not in a
        assert "tagline_es" not in a
        # Telemetry is still present.
        assert "total_runs_in_window" in a


@pytest.mark.asyncio
async def test_per_run_detail_superintendent_403(secret_app, test_database_url):
    ids = await _seed_baseline(test_database_url)
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(
            f"/v1/internal/cockpit/agents/triage/runs/{ids[0]}",
            headers=hdr("sbs:superintendent"),
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_per_run_detail_it_stripped(secret_app, test_database_url):
    ids = await _seed_baseline(test_database_url)
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(
            f"/v1/internal/cockpit/agents/triage/runs/{ids[0]}",
            headers=hdr("sbs:sbs_it"),
        )
    assert r.status_code == 200
    d = r.json()
    assert "complaint_id" not in d
    assert "output" not in d
    assert "tool_calls" not in d
    assert d["model_id"] == "qwen2.5-14b-onprem"  # telemetry yes


@pytest.mark.asyncio
async def test_per_run_detail_conduct_full(secret_app, test_database_url):
    ids = await _seed_baseline(test_database_url)
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(
            f"/v1/internal/cockpit/agents/triage/runs/{ids[0]}",
            headers=hdr("sbs:conduct:analyst"),
        )
    assert r.status_code == 200
    d = r.json()
    assert d["complaint_id"] == "BCO-2026-000001"
    assert "tool_calls" in d
    assert d["model_provider"] == "on_prem"
