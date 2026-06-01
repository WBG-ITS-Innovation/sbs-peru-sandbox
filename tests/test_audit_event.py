"""Tests for the cross-screen audit chain.

Covers the helper-level contract (rejects bad actor_type, builds the row
with the expected fields) and — gated on Docker — the live-DB round-trip
that proves the row lands in Postgres, the kebab-case check constraint
fires, and the actor / object indexes can serve the audit-screen queries.
"""

from __future__ import annotations

import pytest

from sbs_api.audit import record_audit_event
from sbs_api.db.models.audit_event import AuditEvent
from tests.conftest import pytestmark_db


class _CollectingSession:
    """Drop-in for the small surface of AsyncSession the helper touches.

    Only ``add`` is used pre-commit; the live-DB test exercises the real
    commit path.
    """

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)


@pytest.mark.asyncio
async def test_record_audit_event_rejects_bad_actor_type() -> None:
    session = _CollectingSession()
    with pytest.raises(ValueError, match="actor_type"):
        await record_audit_event(
            session,  # type: ignore[arg-type]
            actor_type="bot",  # type: ignore[arg-type]
            actor_id="ml-pipeline",
            action="run-classifier",
            object_type="complaint",
            object_id="BCO-2026-000001",
        )
    assert session.added == []


@pytest.mark.asyncio
async def test_record_audit_event_builds_unsaved_row_with_expected_fields() -> None:
    """The helper writes through to ``session.add`` with the right shape."""

    session = _CollectingSession()
    event = await record_audit_event(
        session,  # type: ignore[arg-type]
        actor_type="user",
        actor_id="supervisor@sandbox.example.com",
        action="switch-persona",
        object_type="session",
        object_id="session-abc-123",
        meta={"from": "supervisor@sandbox.example.com", "to": "analyst@sandbox.example.com"},
    )

    assert isinstance(event, AuditEvent)
    assert session.added == [event]
    assert event.actor_type == "user"
    assert event.actor_id == "supervisor@sandbox.example.com"
    assert event.action == "switch-persona"
    assert event.object_type == "session"
    assert event.object_id == "session-abc-123"
    assert event.diff is None
    assert event.meta == {"from": "supervisor@sandbox.example.com", "to": "analyst@sandbox.example.com"}


@pytestmark_db
async def test_audit_event_round_trip_against_live_db(
    test_database_url: str, db_schema
) -> None:
    """A row written via the helper is queryable and indexes serve actor/object filters."""

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(test_database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            await record_audit_event(
                session,
                actor_type="user",
                actor_id="supervisor@sandbox.example.com",
                action="switch-persona",
                object_type="session",
                object_id="session-abc-123",
                meta={"from": "supervisor@sandbox.example.com", "to": "analyst@sandbox.example.com"},
            )
            await session.commit()

        async with session_maker() as session:
            actor_rows = (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.actor_id == "supervisor@sandbox.example.com"
                    )
                )
            ).scalars().all()
            object_rows = (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.object_id == "session-abc-123"
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    assert len(actor_rows) == 1
    assert actor_rows[0].action == "switch-persona"
    assert len(object_rows) == 1
    assert object_rows[0].id == actor_rows[0].id


@pytestmark_db
async def test_audit_event_rejects_non_kebab_action_at_db_level(
    test_database_url: str, db_schema
) -> None:
    """The kebab-case check constraint fires for badly-cased actions."""

    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(test_database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            await record_audit_event(
                session,
                actor_type="user",
                actor_id="supervisor@sandbox.example.com",
                action="SwitchPersona",  # PascalCase — must be rejected.
                object_type="session",
                object_id="session-xyz",
            )
            with pytest.raises(IntegrityError):
                await session.commit()
    finally:
        await engine.dispose()
