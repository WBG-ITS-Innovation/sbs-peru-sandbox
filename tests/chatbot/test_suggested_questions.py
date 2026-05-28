"""Persona-suggested chatbot questions (P-RESHAPE-9).

Each persona gets its own workflow-tuned list; SBS IT questions are
ops-oriented and Conduct questions are business-oriented.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from sbs_api.agents.insight_chatbot_suggestions import PERSONA_SUGGESTED_QUESTIONS
from sbs_api.auth.persona_scopes import (
    ROLE_ANALYST,
    ROLE_SBS_IT,
    ROLE_SUPERINTENDENT,
    ROLE_SUPERVISOR,
    ROLE_UNIT_HEAD,
)
from tests.chatbot.conftest import hdr
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


@pytest.mark.parametrize(
    "role",
    [
        ROLE_ANALYST,
        ROLE_SUPERVISOR,
        ROLE_UNIT_HEAD,
        ROLE_SUPERINTENDENT,
        ROLE_SBS_IT,
    ],
)
@pytest.mark.asyncio
async def test_each_persona_gets_its_own_list(secret_app, role):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/v1/chatbot/suggested_questions", headers=hdr(role))
    assert r.status_code == 200
    body = r.json()
    assert body["persona"] == role
    assert body["questions"] == PERSONA_SUGGESTED_QUESTIONS[role]
    assert len(body["questions"]) == 3


@pytest.mark.asyncio
async def test_it_questions_are_ops_oriented(secret_app):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        it = await c.get("/v1/chatbot/suggested_questions", headers=hdr(ROLE_SBS_IT))
    text = " ".join(it.json()["questions"]).lower()
    assert "webhook" in text or "ingesta" in text or "agentes" in text


@pytest.mark.asyncio
async def test_conduct_questions_are_business_oriented(secret_app):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        an = await c.get(
            "/v1/chatbot/suggested_questions", headers=hdr(ROLE_ANALYST)
        )
    text = " ".join(an.json()["questions"]).lower()
    assert "queja" in text  # complaint-oriented
