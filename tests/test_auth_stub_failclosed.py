"""Foot-gun mitigation: tenant-requiring endpoints fail closed without auth.

After workstream F.7 the protected routes use the real auth chain
(mTLS → OAuth → rate limit). The "fail closed" behaviour is now:
* Without an mTLS connection (and ``SBS_API_DISABLE_MTLS_FOR_TESTS=false``,
  ``SBS_API_MTLS_MODE=disabled``), the route returns 401 ``CERT_REQUIRED``.
* The legacy auth-stub remains importable for non-protected paths and
  for any test fixture that wants the old AuthContext shape, but
  protected routes do not consult it any more.

The test exercises the new failure mode so "forgot to wire mTLS" surfaces
immediately at startup, not at the first real request in staging.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
async def no_auth_client(monkeypatch):
    monkeypatch.setenv("SBS_API_AUTH_STUB_ENABLED", "false")
    monkeypatch.setenv("SBS_API_MTLS_MODE", "disabled")
    monkeypatch.setenv("SBS_API_DISABLE_MTLS_FOR_TESTS", "false")
    monkeypatch.setenv("SBS_API_LOG_FORMAT", "json")
    monkeypatch.setenv("SBS_API_OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "test")
    monkeypatch.setenv("SBS_API_IDEMPOTENCY_SWEEP_ENABLED", "false")

    from sbs_api.app import create_app
    from sbs_api.config import get_settings

    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    get_settings.cache_clear()


async def test_complaints_list_401_when_mtls_unconfigured(no_auth_client):
    r = await no_auth_client.get("/v1/complaints")
    assert r.status_code == 401
    body = r.json()
    assert body["code"] == "SBS-401-001"
    assert "CERT_REQUIRED" in body["type"]
    assert r.headers.get("content-type", "").startswith("application/problem+json")


async def test_institution_status_401_when_mtls_unconfigured(no_auth_client):
    r = await no_auth_client.get("/v1/institutions/SBS-001234/status")
    assert r.status_code == 401
    assert r.json()["code"] == "SBS-401-001"


async def test_health_live_still_200_without_auth(no_auth_client):
    # Liveness has no auth requirement — orchestrator must always be able to
    # decide whether to restart the pod.
    r = await no_auth_client.get("/v1/health/live")
    assert r.status_code == 200
