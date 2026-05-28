"""Insight-chatbot rate-limit + abuse guards (P-RESHAPE-7)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.agents.insight_chatbot_limits import (
    PER_SESSION_MESSAGES,
    SESSION_IDLE_TIMEOUT,
    check_message_allowed,
)
from sbs_api.db.models.chatbot_session import ChatbotSession
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

NOW = datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc)


async def _seed_session(session, *, user_id="lucia", **kw) -> ChatbotSession:
    sid = str(uuid.uuid4())
    defaults = dict(
        session_id=sid,
        user_id=user_id,
        persona="sbs:conduct:analyst",
        started_at=NOW,
        last_activity_at=NOW,
        ended_at=None,
        message_count=0,
    )
    defaults.update(kw)
    row = ChatbotSession(**defaults)
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_session_message_cap_blocks(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            chat = await _seed_session(
                session, message_count=PER_SESSION_MESSAGES
            )
            decision = await check_message_allowed(
                session, user_id="lucia", chat_session=chat, now=NOW
            )
    finally:
        await engine.dispose()
    assert decision.allowed is False
    assert decision.reason == "session_message_cap"


@pytest.mark.asyncio
async def test_idle_timeout_blocks(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            chat = await _seed_session(
                session,
                last_activity_at=NOW - SESSION_IDLE_TIMEOUT - timedelta(minutes=1),
            )
            decision = await check_message_allowed(
                session, user_id="lucia", chat_session=chat, now=NOW
            )
    finally:
        await engine.dispose()
    assert decision.allowed is False
    assert decision.reason == "session_idle_timeout"


@pytest.mark.asyncio
async def test_ended_session_blocks(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            chat = await _seed_session(session, ended_at=NOW)
            decision = await check_message_allowed(
                session, user_id="lucia", chat_session=chat, now=NOW
            )
    finally:
        await engine.dispose()
    assert decision.allowed is False
    assert decision.reason == "session_ended"


@pytest.mark.asyncio
async def test_fresh_session_allowed(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            chat = await _seed_session(session)
            decision = await check_message_allowed(
                session, user_id="lucia", chat_session=chat, now=NOW
            )
    finally:
        await engine.dispose()
    assert decision.allowed is True
