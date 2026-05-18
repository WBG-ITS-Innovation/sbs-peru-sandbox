"""Foot-gun mitigation: tenant-requiring endpoints fail closed without auth.

When ``AUTH_STUB_ENABLED=false`` the stub dependency raises
``AuthenticationNotConfigured`` which the handler renders as 503 with the
stable code ``AUTH_NOT_CONFIGURED``. The production build never starts
without real auth wired, and this test exercises the failure mode so
"forgot to set the flag in dev" surfaces immediately, not at the first
real request in staging.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
async def no_auth_client(monkeypatch):
    monkeypatch.setenv("SBS_API_AUTH_STUB_ENABLED", "false")
    monkeypatch.setenv("SBS_API_LOG_FORMAT", "json")
    monkeypatch.setenv("SBS_API_OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "test")

    from sbs_api.app import create_app
    from sbs_api.config import get_settings

    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    get_settings.cache_clear()


async def test_complaints_list_503_when_auth_unconfigured(no_auth_client):
    r = await no_auth_client.get("/v1/complaints")
    assert r.status_code == 503
    body = r.json()
    assert body["code"] == "SBS-503-002"
    assert body["status"] == 503
    assert "AUTH_NOT_CONFIGURED" in body["type"]
    assert r.headers.get("content-type", "").startswith("application/problem+json")


async def test_institution_status_503_when_auth_unconfigured(no_auth_client):
    r = await no_auth_client.get("/v1/institutions/SBS-001234/status")
    assert r.status_code == 503
    assert r.json()["code"] == "SBS-503-002"


async def test_health_live_still_200_without_auth(no_auth_client):
    # Liveness has no auth requirement — orchestrator must always be able to
    # decide whether to restart the pod.
    r = await no_auth_client.get("/v1/health/live")
    assert r.status_code == 200
