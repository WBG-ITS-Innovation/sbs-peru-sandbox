# SPDX-License-Identifier: Apache-2.0
"""Dev-only persona auth stub (P-RESHAPE-8.6).

Each persona's ``Bearer stub:<id>`` token resolves to the right scope
set; stub auth is rejected unless BOTH auth_stub_enabled AND
environment==dev; an unknown persona returns 401; and the real
shared-secret path still works in dev alongside the stub.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from sbs_api.auth.persona_scopes import (
    AGENTS_READ,
    OPS_READ,
    ROLE_ANALYST,
    ROLE_SBS_IT,
    ROLE_SUPERINTENDENT,
    ROLE_UNIT_HEAD,
    scopes_for_roles,
)
from tests.conftest import pytestmark_db

SHARED_VAL = "sandbox-stub-auth-test-001"  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# Pure resolver unit tests (no DB)
# ---------------------------------------------------------------------------


def _settings(*, enabled: bool, environment: str):
    class _S:
        pass

    s = _S()
    s.auth_stub_enabled = enabled
    s.environment = environment
    return s


def _request_with(token: str):
    class _R:
        headers = {"authorization": token}

    return _R()


def test_each_persona_resolves_to_its_scope_set():
    from sbs_api.dependencies.auth_stub import STUB_PERSONA_ROLES, resolve_stub

    settings = _settings(enabled=True, environment="dev")
    for persona, role in STUB_PERSONA_ROLES.items():
        principal = resolve_stub(_request_with(f"Bearer stub:{persona}"), settings)
        assert principal is not None
        assert principal.persona == role
        assert principal.username == persona
        assert principal.user_id == f"stub-{persona}"
        assert principal.scopes == scopes_for_roles(frozenset({role}))


def test_stub_ignored_when_flag_off():
    from sbs_api.dependencies.auth_stub import resolve_stub

    settings = _settings(enabled=False, environment="dev")
    assert resolve_stub(_request_with("Bearer stub:jorge"), settings) is None


def test_stub_ignored_in_prod_even_if_flag_on():
    from sbs_api.dependencies.auth_stub import resolve_stub

    settings = _settings(enabled=True, environment="prod")
    assert resolve_stub(_request_with("Bearer stub:jorge"), settings) is None


def test_unknown_persona_raises_401():
    from fastapi import HTTPException

    from sbs_api.dependencies.auth_stub import resolve_stub

    settings = _settings(enabled=True, environment="dev")
    with pytest.raises(HTTPException) as exc:
        resolve_stub(_request_with("Bearer stub:ghost"), settings)
    assert exc.value.status_code == 401


def test_non_stub_bearer_is_not_a_stub():
    from sbs_api.dependencies.auth_stub import resolve_stub

    settings = _settings(enabled=True, environment="dev")
    assert resolve_stub(_request_with("Bearer real.jwt.token"), settings) is None


# ---------------------------------------------------------------------------
# App-level: stub tokens drive real route scope checks (dev + flag on)
# ---------------------------------------------------------------------------

pytestmark = pytestmark_db


@pytest.fixture
async def dev_stub_app(app_settings, monkeypatch, db_schema):
    monkeypatch.setenv("SBS_API_AUTH_STUB_ENABLED", "true")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "dev")
    monkeypatch.setenv("SBS_API_INTERNAL_API_SECRET", SHARED_VAL)
    monkeypatch.setenv("SBS_API_DISABLE_MTLS_FOR_TESTS", "true")
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


@pytest.mark.asyncio
async def test_stub_sergio_denied_on_complaints(dev_stub_app):
    transport = ASGITransport(app=dev_stub_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(
            "/v1/complaints",
            headers={"Authorization": "Bearer stub:sergio"},
        )
    # Sergio holds no institution complaints:read scope → 403 (scope
    # enforced, not stub-blind 200).
    assert r.status_code == 403
