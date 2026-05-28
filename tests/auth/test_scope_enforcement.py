"""Persona scope matrix + route-level 403 enforcement (P-RESHAPE-5).

Pure-unit half: assert the locked role→scope map. App half: assert the
``requires_scope`` dependency 403s a role that lacks the scope and
admits one that holds it.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from sbs_api.auth.persona_scopes import (
    AUDIT_READ,
    COMPLAINTS_READ_DETAIL,
    EXEC_READ,
    FI_BRIEF_APPROVE,
    FI_BRIEF_OVERRIDE,
    OPS_READ,
    PEER_RISK_READ_EXEC,
    ROLE_ANALYST,
    ROLE_SBS_IT,
    ROLE_SUPERINTENDENT,
    ROLE_SUPERVISOR,
    ROLE_UNIT_HEAD,
    scopes_for_roles,
)
from tests.conftest import pytestmark_db

SHARED_VAL = "sandbox-persona-scope-test-001"  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# Pure scope-map matrix (no DB)
# ---------------------------------------------------------------------------


def test_analyst_has_complaint_detail_not_approve():
    s = scopes_for_roles(frozenset({ROLE_ANALYST}))
    assert COMPLAINTS_READ_DETAIL in s
    assert FI_BRIEF_APPROVE not in s
    assert OPS_READ not in s
    assert EXEC_READ not in s


def test_supervisor_can_approve_not_override():
    s = scopes_for_roles(frozenset({ROLE_SUPERVISOR}))
    assert FI_BRIEF_APPROVE in s
    assert FI_BRIEF_OVERRIDE not in s
    assert OPS_READ not in s


def test_unit_head_can_override():
    s = scopes_for_roles(frozenset({ROLE_UNIT_HEAD}))
    assert FI_BRIEF_OVERRIDE in s
    assert AUDIT_READ in s


def test_superintendent_is_exec_only_no_detail():
    s = scopes_for_roles(frozenset({ROLE_SUPERINTENDENT}))
    assert EXEC_READ in s
    assert PEER_RISK_READ_EXEC in s
    assert COMPLAINTS_READ_DETAIL not in s
    assert FI_BRIEF_APPROVE not in s
    assert OPS_READ not in s


def test_sbs_it_is_ops_only_no_business():
    s = scopes_for_roles(frozenset({ROLE_SBS_IT}))
    assert OPS_READ in s
    assert COMPLAINTS_READ_DETAIL not in s
    assert FI_BRIEF_APPROVE not in s
    assert EXEC_READ not in s


def test_unknown_role_grants_nothing():
    assert scopes_for_roles(frozenset({"sbs:wb_reviewer"})) == frozenset()


# ---------------------------------------------------------------------------
# App-level 403 enforcement
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
async def test_analyst_cannot_hit_ops_endpoint(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/v1/internal/ops/agent_health", headers=_hdr(ROLE_ANALYST))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_it_can_hit_ops_endpoint(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/v1/internal/ops/agent_health", headers=_hdr(ROLE_SBS_IT))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_it_cannot_hit_exec_endpoint(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(
            "/v1/internal/exec/cohort_health", headers=_hdr(ROLE_SBS_IT)
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_superintendent_can_hit_exec_endpoint(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(
            "/v1/internal/exec/cohort_health", headers=_hdr(ROLE_SUPERINTENDENT)
        )
    assert r.status_code == 200
