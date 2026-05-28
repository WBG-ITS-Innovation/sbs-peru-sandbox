"""Persona data-filter sentinels (P-RESHAPE-5).

Pure-unit half: the field-stripping + assertion helpers. App half:
Lucía cannot approve an FIBrief; IT/exec responses carry no business
fields.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from sbs_api.dependencies.persona import (
    assert_no_business_fields,
    assert_no_per_complaint_or_narrative,
    strip_business_fields,
)
from sbs_api.auth.persona_scopes import (
    ROLE_ANALYST,
    ROLE_SBS_IT,
    ROLE_SUPERINTENDENT,
)
from tests.conftest import pytestmark_db

SHARED_VAL = "sandbox-persona-filter-test-001"  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# Pure helpers (no DB)
# ---------------------------------------------------------------------------


def test_assert_no_business_fields_raises_on_narrative():
    with pytest.raises(AssertionError):
        assert_no_business_fields({"ok": 1, "narrative_es": "leaked"})


def test_assert_no_business_fields_passes_for_ops_payload():
    assert_no_business_fields(
        {"institution_id": "SBS-001234", "lag_hours": 3.0, "status": "AMBER"}
    )


def test_assert_no_business_fields_recurses_into_lists():
    with pytest.raises(AssertionError):
        assert_no_business_fields(
            {"items": [{"institution_id": "x"}, {"motivo_code": "COBRO_INDEBIDO"}]}
        )


def test_strip_business_fields_removes_keys():
    cleaned = strip_business_fields(
        {"keep": 1, "motivo_code": "X", "nested": {"narrative": "y", "z": 2}}
    )
    assert cleaned == {"keep": 1, "nested": {"z": 2}}


def test_exec_sentinel_allows_aggregate_category_but_not_complaint_id():
    # Aggregate category counts are allowed at exec level.
    assert_no_per_complaint_or_narrative(
        {"by_category_count": {"COBRO_INDEBIDO": 4}}
    )
    # A per-complaint id is not.
    with pytest.raises(AssertionError):
        assert_no_per_complaint_or_narrative({"complaint_id": "BCO-2026-000001"})


# ---------------------------------------------------------------------------
# App-level enforcement
# ---------------------------------------------------------------------------

pytestmark = pytestmark_db


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


def _hdr(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {SHARED_VAL}", "X-SBS-Role": role}


@pytest.mark.asyncio
async def test_analyst_cannot_approve_fi_brief(app_with_secret):
    """Lucía (analyst) lacks fi_brief:approve → 403 on the approve route."""
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            "/v1/internal/fi_briefs/any-brief-id/approve",
            json={"actor_id": "lucia", "rationale": "x" * 25},
            headers=_hdr(ROLE_ANALYST),
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_it_telemetry_carries_no_business_fields(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for path in (
            "/v1/internal/ops/ingestion_lag",
            "/v1/internal/ops/agent_health",
            "/v1/internal/ops/webhook_health",
            "/v1/internal/ops/model_routing",
            "/v1/internal/ops/error_tail",
        ):
            r = await c.get(path, headers=_hdr(ROLE_SBS_IT))
            assert r.status_code == 200, path
            # The handler already self-checks; re-assert here for the sentinel.
            assert_no_business_fields(r.json())


@pytest.mark.asyncio
async def test_exec_endpoints_carry_no_per_complaint_or_narrative(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        for path in (
            "/v1/internal/exec/cohort_health",
            "/v1/internal/exec/top_patterns_summary",
            "/v1/internal/exec/fi_brief_activity_aggregate",
        ):
            r = await c.get(path, headers=_hdr(ROLE_SUPERINTENDENT))
            assert r.status_code == 200, path
            assert_no_per_complaint_or_narrative(r.json())
