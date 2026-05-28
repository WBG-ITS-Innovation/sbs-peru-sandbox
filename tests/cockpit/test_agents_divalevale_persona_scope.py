"""DIValeVale cockpit endpoint persona scoping (P-RESHAPE-8).

Sergio (Superintendent) lacks agents:read → 403. Rosa (IT) gets
telemetry only (no institution_code / per-rule detail). Lucía (Analyst)
sees only her assigned FIs. Jorge (Unit Head) sees full detail.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.db.models.validation_audit import ValidationAudit
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

SHARED_VAL = "sandbox-divalevale-scope-001"  # pragma: allowlist secret
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


async def _seed_audit(test_database_url, *, institution_code, audit_id=None) -> str:
    aid = audit_id or str(uuid.uuid4())
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    async with SM() as session:
        session.add(
            ValidationAudit(
                audit_id=aid,
                complaint_id="BCO-2026-000004",
                institution_code=institution_code,
                received_at=NOW,
                verdict="INSUFFICIENT",
                pass1_failed_rules=["NARRATIVE_TOO_SHORT"],
                pass2_invoked=False,
                routing_action="FLAGGED_FOR_ENRICHMENT",
                model_id="divalevale",
                model_provider="onprem",
                tier="TIER_1",
                latency_ms=12,
            )
        )
        await session.commit()
    await engine.dispose()
    return aid


def _hdr(role: str, **extra) -> dict[str, str]:
    h = {"Authorization": f"Bearer {SHARED_VAL}", "X-SBS-Role": role}
    h.update(extra)
    return h


@pytest.mark.asyncio
async def test_superintendent_denied(app_with_secret, test_database_url):
    await _seed_audit(test_database_url, institution_code="SBS-001234")
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(
            "/v1/internal/cockpit/agents/divalevale/activity",
            headers=_hdr("sbs:superintendent"),
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_it_gets_telemetry_only(app_with_secret, test_database_url):
    aid = await _seed_audit(test_database_url, institution_code="SBS-001234")
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        act = await c.get(
            "/v1/internal/cockpit/agents/divalevale/activity",
            headers=_hdr("sbs:sbs_it"),
        )
        detail = await c.get(
            f"/v1/internal/cockpit/agents/divalevale/runs/{aid}",
            headers=_hdr("sbs:sbs_it"),
        )
    assert act.status_code == 200
    # IT recent_runs carry no business fields.
    for run in act.json()["recent_runs"]:
        assert "institution_code" not in run
        assert "complaint_id" not in run
    assert detail.status_code == 200
    d = detail.json()
    assert "institution_code" not in d
    assert "pass1_failed_rules" not in d
    assert "latency_ms" in d  # telemetry yes


@pytest.mark.asyncio
async def test_unit_head_sees_full_detail(app_with_secret, test_database_url):
    aid = await _seed_audit(test_database_url, institution_code="SBS-001234")
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        detail = await c.get(
            f"/v1/internal/cockpit/agents/divalevale/runs/{aid}",
            headers=_hdr("sbs:conduct:head"),
        )
    assert detail.status_code == 200
    d = detail.json()
    assert d["institution_code"] == "SBS-001234"
    assert d["pass1_failed_rules"] == ["NARRATIVE_TOO_SHORT"]


@pytest.mark.asyncio
async def test_analyst_scoped_to_assigned_fis(app_with_secret, test_database_url):
    # Audit row on an FI the analyst is NOT assigned → filtered out.
    aid = await _seed_audit(test_database_url, institution_code="SBS-999999")
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        act = await c.get(
            "/v1/internal/cockpit/agents/divalevale/activity",
            headers=_hdr("sbs:conduct:analyst", **{"X-SBS-FI": "SBS-001234"}),
        )
        detail = await c.get(
            f"/v1/internal/cockpit/agents/divalevale/runs/{aid}",
            headers=_hdr("sbs:conduct:analyst", **{"X-SBS-FI": "SBS-001234"}),
        )
    assert act.status_code == 200
    assert act.json()["total_runs"] == 0  # the SBS-999999 row is filtered out
    assert detail.status_code == 404  # not her FI
