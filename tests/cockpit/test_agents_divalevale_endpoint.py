"""DIValeVale cockpit activity endpoint returns real aggregates (P-RESHAPE-8)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.db.models.validation_audit import ValidationAudit
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

SHARED_VAL = "sandbox-divalevale-endpoint-001"  # pragma: allowlist secret
NOW = datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def app_with_secret(app_settings, monkeypatch, db_schema):
    monkeypatch.setenv("SBS_API_INTERNAL_API_SECRET", SHARED_VAL)
    from sbs_api.config import get_settings

    get_settings.cache_clear()
    from sbs_api.app import create_app
    from sbs_api.db.session import reset_engine_for_test

    await reset_engine_for_test()
    application = create_app(settings=get_settings())
    try:
        yield application
    finally:
        await reset_engine_for_test()
        get_settings.cache_clear()


async def _seed(test_database_url) -> None:
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    async with SM() as session:
        for verdict, action, lat in [
            ("VALID", "PROCEEDED_TO_TRIAGE", 10),
            ("VALID", "PROCEEDED_TO_TRIAGE", 20),
            ("INSUFFICIENT", "FLAGGED_FOR_ENRICHMENT", 30),
            ("INVALID", "REJECTED", 5),
        ]:
            session.add(
                ValidationAudit(
                    audit_id=str(uuid.uuid4()),
                    complaint_id=None,
                    institution_code="SBS-001234",
                    received_at=NOW,
                    verdict=verdict,
                    pass1_failed_rules=[],
                    pass2_invoked=False,
                    routing_action=action,
                    model_id="divalevale",
                    model_provider="onprem",
                    tier="TIER_1",
                    latency_ms=lat,
                )
            )
        await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_activity_aggregates(app_with_secret, test_database_url):
    await _seed(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(
            "/v1/internal/cockpit/agents/divalevale/activity?window=24h",
            headers={"Authorization": f"Bearer {SHARED_VAL}", "X-SBS-Role": "sbs:conduct:head"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["total_runs"] == 4
    assert body["by_verdict"]["VALID"] == 2
    assert body["by_routing_action"]["FLAGGED_FOR_ENRICHMENT"] == 1
    assert body["success_rate"] == round(2 / 4, 3)
    assert body["p50_latency_ms"] is not None
    assert body["p95_latency_ms"] is not None
    assert body["current_status"] == "RUNNING"
