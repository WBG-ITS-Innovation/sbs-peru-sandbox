"""Tests for the supervisor-UI cockpit data endpoint.

Covers the shared-secret auth gate and the snapshot shape against a
live testcontainer DB with seeded institutions + complaints + one
seeded cross-source-correlator agent run (the anomaly card).
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


@pytest.fixture
def internal_secret() -> str:
    return "sandbox-cockpit-secret-abcdef0123456789"  # pragma: allowlist secret


@pytest.fixture
async def app_with_secret(app_settings, monkeypatch, internal_secret, db_schema):
    monkeypatch.setenv("SBS_API_INTERNAL_API_SECRET", internal_secret)
    from sbs_api.config import get_settings

    get_settings.cache_clear()
    from sbs_api.app import create_app

    fresh = get_settings()
    application = create_app(settings=fresh)
    yield application
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_cockpit_returns_snapshot_with_tier_panels(
    app_with_secret, internal_secret
):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/internal/cockpit",
            headers={"Authorization": f"Bearer {internal_secret}"},
        )
    assert response.status_code == 200, response.text
    body = response.json()

    assert "generated_at" in body
    assert "kpis" in body
    assert "tier1" in body and "tier2" in body
    assert body["tier1"]["tier_label"] == "Tier 1"
    assert body["tier2"]["tier_label"] == "Tier 2"
    assert body["tier1"]["institution_id"] == "SBS-001234"
    assert body["tier2"]["institution_id"] == "SBS-005678"
    # The conftest seeds three complaints on SBS-001234, all in May
    # 2026 — they will appear on the Tier 1 panel.
    assert isinstance(body["tier1"]["recent"], list)
    # Cross-source strip carries exactly five channels.
    assert len(body["cross_source"]["channels"]) == 5
    keys = {c["key"] for c in body["cross_source"]["channels"]}
    assert keys == {"complaints", "social", "indecopi", "plavia", "internal"}
    assert body["cross_source"]["is_illustrative"] is True
    # KPI strip has a sparkline (24 hourly values).
    assert len(body["kpis"]["complaints_24h_sparkline"]) == 24


@pytest.mark.asyncio
async def test_cockpit_endpoint_rejects_missing_authorization(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/internal/cockpit")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cockpit_endpoint_rejects_wrong_secret(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/internal/cockpit",
            headers={"Authorization": "Bearer wrong"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cockpit_surfaces_seeded_anomaly_when_present(
    app_with_secret, internal_secret, test_database_url
):
    """A seeded cross-source-correlator run with anomaly_flag=true must
    appear on the cockpit's anomalies array — this is the link between
    WS0's seed and the WS3 cockpit's anomaly card."""

    from datetime import datetime, timezone

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.agent_run import AgentRun

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionMaker() as session:
        session.add(
            AgentRun(
                id="test-anom-1",
                complaint_id="BCO-2026-000001",
                agent_name="cross-source-correlator",
                agent_version="cross-source-correlator-0.2.0",
                started_at=datetime.now(tz=timezone.utc),
                ended_at=datetime.now(tz=timezone.utc),
                status="success",
                tool_calls=[],
                final_output={
                    "composite_score": 0.74,
                    "threshold": 0.7,
                    "channel_contributions": [
                        {"channel": "complaints", "value": 0.62, "contribution": 0.18},
                        {"channel": "indecopi", "value": 0.55, "contribution": 0.30},
                    ],
                    "anomaly_flag": True,
                },
                error=None,
            )
        )
        await session.commit()
    await engine.dispose()

    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/internal/cockpit",
            headers={"Authorization": f"Bearer {internal_secret}"},
        )
    body = response.json()
    assert len(body["anomalies"]) >= 1
    a = body["anomalies"][0]
    assert a["composite_score"] == 0.74
    assert a["threshold"] == 0.7
    assert len(a["channel_contributions"]) == 2
