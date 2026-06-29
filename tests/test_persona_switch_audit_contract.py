# SPDX-License-Identifier: Apache-2.0
"""Contract test for the persona-switcher audit row.

The switcher lives in the Next.js process (app/src/app/api/persona/switch).
This test does NOT exercise the TypeScript code directly — it locks the
audit-row SHAPE the switcher writes through ``record_audit_event`` so a
refactor on the TypeScript side cannot silently degrade the audit
chain. If you change the meta keys here, change them in
``app/src/app/api/persona/switch/route.ts`` in the same PR.

The user-facing reading test guards against is: a row that says
"An operator switched persona at 14:32" is useless audit data; the row
must carry from_persona AND to_persona so an auditor can reconstruct
the transition.
"""

from __future__ import annotations

import pytest

from sbs_api.audit import record_audit_event
from sbs_api.db.models.audit_event import AuditEvent
from tests.conftest import pytestmark_db


@pytest.mark.asyncio
async def test_switch_persona_row_carries_from_and_to() -> None:
    """Any switch row must have meta.from_persona and meta.to_persona —
    without those two keys, the audit trail is meaningless."""

    class _Collector:
        def __init__(self) -> None:
            self.added: list = []

        def add(self, obj: object) -> None:
            self.added.append(obj)

    session = _Collector()
    event = await record_audit_event(
        session,  # type: ignore[arg-type]
        actor_type="user",
        actor_id="operator",
        action="switch-persona",
        object_type="session",
        object_id="session-abc-123",
        meta={
            "from_persona": "maria",
            "from_email": "maria@sandbox.example.com",
            "to_persona": "jorge",
            "to_email": "jorge@sandbox.example.com",
        },
    )
    assert isinstance(event, AuditEvent)
    assert event.action == "switch-persona"
    assert event.actor_id == "operator", (
        "operator must be the actor; using the persona's email would lose "
        "the 'who triggered the switch' signal from the audit"
    )
    assert event.meta is not None
    assert event.meta.get("from_persona") == "maria"
    assert event.meta.get("to_persona") == "jorge"
    assert event.meta.get("from_email") == "maria@sandbox.example.com"
    assert event.meta.get("to_email") == "jorge@sandbox.example.com"


@pytestmark_db
async def test_switch_persona_row_round_trips_against_live_db(
    test_database_url: str, db_schema
) -> None:
    """Write a switch row through the helper, read it back, check the
    meta payload is intact and queryable."""

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(test_database_url)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_maker() as session:
            await record_audit_event(
                session,
                actor_type="user",
                actor_id="operator",
                action="switch-persona",
                object_type="session",
                object_id="session-abc-123",
                meta={
                    "from_persona": "maria",
                    "from_email": "maria@sandbox.example.com",
                    "to_persona": "lucia",
                    "to_email": "lucia@sandbox.example.com",
                },
            )
            await session.commit()

        async with session_maker() as session:
            rows = (
                await session.execute(
                    select(AuditEvent).where(AuditEvent.action == "switch-persona")
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    assert len(rows) == 1
    row = rows[0]
    assert row.actor_id == "operator"
    assert row.meta == {
        "from_persona": "maria",
        "from_email": "maria@sandbox.example.com",
        "to_persona": "lucia",
        "to_email": "lucia@sandbox.example.com",
    }
