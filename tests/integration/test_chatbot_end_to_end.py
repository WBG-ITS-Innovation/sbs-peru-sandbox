"""Insight-chatbot end-to-end via the FastAPI app (P-RESHAPE-7).

Covers session create → message → history → end, the X-SBS-User
ownership check, the PII sentinel on stored content, and the
chatbot:use scope gate.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.db.models.chatbot_session import ChatbotMessage
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

SHARED_VAL = "sandbox-chatbot-e2e-001"  # pragma: allowlist secret


@pytest.fixture
async def app_with_secret(app_settings, monkeypatch, db_schema):
    monkeypatch.setenv("SBS_API_INTERNAL_API_SECRET", SHARED_VAL)
    monkeypatch.setenv("SBS_API_MODEL_PROVIDER", "mock")
    from sbs_api.config import get_settings

    get_settings.cache_clear()
    from sbs_api.agents.providers import reset_provider_cache
    from sbs_api.app import create_app
    from sbs_api.db.session import reset_engine_for_test

    reset_provider_cache()
    await reset_engine_for_test()
    application = create_app(settings=get_settings())
    try:
        yield application
    finally:
        await reset_engine_for_test()
        get_settings.cache_clear()


def _hdr(user: str, role: str = "sbs:conduct:analyst") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {SHARED_VAL}",
        "X-SBS-Role": role,
        "X-SBS-User": user,
    }


@pytest.mark.asyncio
async def test_session_lifecycle_and_redaction(app_with_secret, test_database_url):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # create
        r = await c.post("/v1/chatbot/sessions", headers=_hdr("lucia"))
        assert r.status_code == 201
        sid = r.json()["session_id"]
        assert r.json()["persona"] == "sbs:conduct:analyst"

        # post a message containing PII — must be redacted before storage
        msg = await c.post(
            f"/v1/chatbot/sessions/{sid}/messages",
            json={
                "content": "Mi DNI es 12345678 y mi teléfono 987654321, "
                "muéstrame patrones."
            },
            headers=_hdr("lucia"),
        )
        assert msg.status_code == 200
        body = msg.json()
        assert "answer_text_es" in body
        assert "citations" in body
        assert body["persona"] == "sbs:conduct:analyst"

        # history
        hist = await c.get(f"/v1/chatbot/sessions/{sid}", headers=_hdr("lucia"))
        assert hist.status_code == 200
        assert len(hist.json()["messages"]) >= 2  # user + assistant

        # end
        ended = await c.delete(f"/v1/chatbot/sessions/{sid}", headers=_hdr("lucia"))
        assert ended.status_code == 200
        assert ended.json()["status"] == "ended"

    # PII sentinel: stored user content carries no DNI / phone digits.
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            rows = (
                await session.execute(
                    select(ChatbotMessage).where(ChatbotMessage.role == "user")
                )
            ).scalars().all()
    finally:
        await engine.dispose()
    assert rows
    for m in rows:
        assert "12345678" not in m.content
        assert "987654321" not in m.content


@pytest.mark.asyncio
async def test_ownership_enforced(app_with_secret, test_database_url):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/v1/chatbot/sessions", headers=_hdr("lucia"))
        sid = r.json()["session_id"]
        # A different user cannot post to lucia's session → 404 (not 403,
        # to avoid leaking session-id existence).
        other = await c.post(
            f"/v1/chatbot/sessions/{sid}/messages",
            json={"content": "hola"},
            headers=_hdr("maria", role="sbs:conduct:supervisor"),
        )
    assert other.status_code == 404


@pytest.mark.asyncio
async def test_missing_user_header_401(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            "/v1/chatbot/sessions",
            headers={"Authorization": f"Bearer {SHARED_VAL}", "X-SBS-Role": "sbs:conduct:analyst"},
        )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_no_persona_role_forbidden(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # An unknown role has no chatbot:use scope → 403.
        r = await c.post(
            "/v1/chatbot/sessions",
            headers={
                "Authorization": f"Bearer {SHARED_VAL}",
                "X-SBS-Role": "sbs:wb_reviewer",
                "X-SBS-User": "ghost",
            },
        )
    assert r.status_code == 403
