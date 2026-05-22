"""Tests for the supervisor-UI-facing audit endpoint.

POST /v1/internal/audit is the single path by which the Next.js
supervisor UI writes to the audit chain. The endpoint is gated by a
shared secret in the Authorization header. The kebab-case shape of
``action`` is enforced by both Pydantic and the DB check constraint.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


@pytest.fixture
def internal_secret() -> str:
    return "sandbox-internal-secret-0123456789abcdef"  # pragma: allowlist secret


@pytest.fixture
async def app_with_internal_secret(app_settings, monkeypatch, internal_secret, db_schema):
    """A FastAPI app configured with the internal-api shared secret."""

    monkeypatch.setenv("SBS_API_INTERNAL_API_SECRET", internal_secret)
    from sbs_api.config import get_settings

    get_settings.cache_clear()
    from sbs_api.app import create_app

    fresh_settings = get_settings()
    application = create_app(settings=fresh_settings)
    yield application
    get_settings.cache_clear()


@pytest.fixture
async def app_without_internal_secret(app_settings, monkeypatch, db_schema):
    """A FastAPI app with no internal secret configured (the safe default)."""

    monkeypatch.delenv("SBS_API_INTERNAL_API_SECRET", raising=False)
    from sbs_api.config import get_settings

    get_settings.cache_clear()
    from sbs_api.app import create_app

    fresh_settings = get_settings()
    application = create_app(settings=fresh_settings)
    yield application
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_audit_post_happy_path(app_with_internal_secret, internal_secret):
    transport = ASGITransport(app=app_with_internal_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/internal/audit",
            headers={"Authorization": f"Bearer {internal_secret}"},
            json={
                "actor_type": "user",
                "actor_id": "maria@sbs.gob.pe",
                "action": "login",
                "object_type": "session",
                "object_id": "session-abc-123",
                "meta": {"roles": ["sbs:conduct:supervisor"]},
            },
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body["id"], int)
    assert "T" in body["created_at"]


@pytest.mark.asyncio
async def test_audit_post_rejects_missing_authorization(app_with_internal_secret):
    transport = ASGITransport(app=app_with_internal_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/internal/audit",
            json={
                "actor_type": "user",
                "actor_id": "maria@sbs.gob.pe",
                "action": "login",
                "object_type": "session",
                "object_id": "session-abc-123",
            },
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_audit_post_rejects_wrong_secret(app_with_internal_secret):
    transport = ASGITransport(app=app_with_internal_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/internal/audit",
            headers={"Authorization": "Bearer wrong-secret"},
            json={
                "actor_type": "user",
                "actor_id": "maria@sbs.gob.pe",
                "action": "login",
                "object_type": "session",
                "object_id": "session-abc-123",
            },
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_audit_post_returns_404_when_secret_not_configured(
    app_without_internal_secret,
):
    """When SBS_API_INTERNAL_API_SECRET is unset, the endpoint is unreachable
    (404), not merely unauthorized. Defends against a misconfigured
    deployment exposing the audit-write path."""

    transport = ASGITransport(app=app_without_internal_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/internal/audit",
            headers={"Authorization": "Bearer anything"},
            json={
                "actor_type": "user",
                "actor_id": "maria@sbs.gob.pe",
                "action": "login",
                "object_type": "session",
                "object_id": "session-abc-123",
            },
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_audit_post_rejects_non_kebab_action(
    app_with_internal_secret, internal_secret
):
    transport = ASGITransport(app=app_with_internal_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/internal/audit",
            headers={"Authorization": f"Bearer {internal_secret}"},
            json={
                "actor_type": "user",
                "actor_id": "maria@sbs.gob.pe",
                "action": "SwitchPersona",
                "object_type": "session",
                "object_id": "session-abc-123",
            },
        )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_audit_post_rejects_invalid_actor_type(
    app_with_internal_secret, internal_secret
):
    transport = ASGITransport(app=app_with_internal_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/internal/audit",
            headers={"Authorization": f"Bearer {internal_secret}"},
            json={
                "actor_type": "bot",
                "actor_id": "ml-pipeline",
                "action": "run-classifier",
                "object_type": "complaint",
                "object_id": "BCO-2026-000001",
            },
        )
    assert response.status_code == 422
