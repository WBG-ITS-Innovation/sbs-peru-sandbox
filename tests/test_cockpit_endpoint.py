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
    from sbs_api.db.session import reset_engine_for_test

    await reset_engine_for_test()
    fresh = get_settings()
    application = create_app(settings=fresh)
    try:
        yield application
    finally:
        await reset_engine_for_test()
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
    # P11 demo-ui-polish overlay — tier labels widened to "Tier 1 NRT"
    # / "Tier 2 Batch" and each panel now carries an explicit
    # ``tier_variant`` so the UI can pick the WBG-palette badge colour.
    assert body["tier1"]["tier_label"] == "Tier 1 NRT"
    assert body["tier2"]["tier_label"] == "Tier 2 Batch"
    assert body["tier1"]["tier_variant"] == "tier1"
    assert body["tier2"]["tier_variant"] == "tier2"
    assert body["tier1"]["institution_id"] == "SBS-001234"
    assert body["tier2"]["institution_id"] == "SBS-005678"
    assert body["tier2"]["institution_name"] == "COOPAC_DEMO_002"
    # The conftest seeds three complaints on SBS-001234 (Tier 1) and
    # three on SBS-005678 (Tier 2). Both panels must reflect their
    # seeded rows — Tier 2 being empty is the P10 demo-data integrity
    # bug we explicitly guard against here.
    assert isinstance(body["tier1"]["recent"], list)
    assert isinstance(body["tier2"]["recent"], list)
    assert len(body["tier1"]["recent"]) >= 3, body["tier1"]["recent"]
    assert len(body["tier2"]["recent"]) >= 3, body["tier2"]["recent"]
    # Every Tier 2 card must come from the SBS-005678 institution; the
    # cockpit query is the source of truth — there are no hardcoded
    # UI cards in the snapshot.
    assert all(
        card["institution_id"] == "SBS-005678"
        for card in body["tier2"]["recent"]
    ), body["tier2"]["recent"]
    # And every Tier 2 card must carry the batch provenance the seed
    # records via source='batch'.
    assert all(
        card["source"] == "batch" for card in body["tier2"]["recent"]
    ), body["tier2"]["recent"]
    # Lastly: no PII-looking value (DNI, phone, email) leaks through
    # the synthetic narrative excerpts.
    import re

    _PII_PATTERNS = (
        re.compile(r"\b\d{8}\b"),
        re.compile(r"\b9\d{8}\b"),
        re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    )
    for card in body["tier2"]["recent"]:
        preview = card.get("description_preview", "")
        for pattern in _PII_PATTERNS:
            assert pattern.search(preview) is None, (
                f"unexpected PII-shaped value in Tier 2 preview: {preview!r}"
            )
    # Cross-source strip carries exactly five channels.
    assert len(body["cross_source"]["channels"]) == 5
    keys = {c["key"] for c in body["cross_source"]["channels"]}
    assert keys == {"complaints", "social", "indecopi", "plavia", "internal"}
    assert body["cross_source"]["is_illustrative"] is True
    # KPI strip has a sparkline (24 hourly values).
    assert len(body["kpis"]["complaints_24h_sparkline"]) == 24


@pytest.mark.asyncio
async def test_taxonomy_stats_endpoint_returns_today_window(
    app_with_secret, internal_secret, test_database_url
):
    """GET /v1/internal/cockpit/taxonomy-stats returns ``normalizations_today``
    and ``institutions_affected`` over the "since 00:00 UTC today" window.

    The endpoint backs the cockpit's "Taxonomy harmonization today" stat
    tile (P11 demo-ui-polish overlay). The fixture seeds one
    ``taxonomy-normalized`` audit row against the seeded BANCO_DEMO_001
    complaint so the counter must be ≥ 1 and the distinct-institution
    count must be ≥ 1.
    """

    from datetime import datetime, timezone

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.audit_event import AuditEvent

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionMaker() as session:
        session.add(
            AuditEvent(
                actor_type="agent",
                actor_id="live-ingestion-orchestrator",
                action="taxonomy-normalized",
                object_type="complaint",
                object_id="BCO-2026-000001",
                diff={
                    "normalizations": [
                        {
                            "field_path": "product",
                            "original_value": "Crédito de consumo",
                            "canonical_value": "credito_consumo",
                            "dictionary_version": "taxonomy-v1",
                        }
                    ]
                },
                meta={"dictionary_version": "taxonomy-v1"},
                created_at=datetime.now(tz=timezone.utc),
            )
        )
        await session.commit()
    await engine.dispose()

    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/internal/cockpit/taxonomy-stats",
            headers={"Authorization": f"Bearer {internal_secret}"},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["normalizations_today"] >= 1
    assert body["institutions_affected"] >= 1
    # Window honesty: the response carries the as-of timestamp the UI
    # tile renders. ISO 8601 with offset.
    assert "T" in body["as_of"]


@pytest.mark.asyncio
async def test_taxonomy_stats_endpoint_rejects_missing_secret(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/internal/cockpit/taxonomy-stats")
    assert response.status_code == 401


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
