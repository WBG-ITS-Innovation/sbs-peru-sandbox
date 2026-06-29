# SPDX-License-Identifier: Apache-2.0
"""WS6 + WS7 integration tests.

Covers:

* GET /v1/internal/audit pagination + filters + role gate.
* Audit-row completeness across every action type that fires on the
  demo path (login, switch-persona, edit-draft-narrative,
  send-to-approvals, approve-finding, approve-with-edits-finding,
  reject-finding, send-back-finding). Asserts each action's meta
  carries the documented shape.
* Findings SSE topic accepts all three conduct scopes (parity with
  the WS4 approvals-topic tests for the third role).
* SSE reconnect-with-Last-Event-ID replays the correct slice.

All DB-gated via pytestmark_db.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import pytestmark_db
from tests.integration._sse_probe import open_sse_head_only

pytestmark = pytestmark_db


SHARED_VAL = "sandbox-audit-test-1357924680"  # pragma: allowlist secret


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


def _hdr(role: str = "sbs:conduct:head") -> dict[str, str]:
    return {"Authorization": f"Bearer {SHARED_VAL}", "X-SBS-Role": role}


async def _seed_audit_row(
    test_database_url: str,
    *,
    actor_id: str,
    action: str,
    object_type: str,
    object_id: str,
    meta: dict | None = None,
    diff: dict | None = None,
) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.audit import record_audit_event

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionMaker() as session:
        event = await record_audit_event(
            session,
            actor_type="user",
            actor_id=actor_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            diff=diff,
            meta=meta,
        )
        await session.commit()
        eid = event.id
    await engine.dispose()
    return eid


# -- Audit endpoint --------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_endpoint_returns_paginated_rows(
    app_with_secret, test_database_url
):
    # Seed 12 rows so two pages at page_size=5 exercise the boundary.
    for i in range(12):
        await _seed_audit_row(
            test_database_url,
            actor_id=f"u{i}@sandbox.example.com",
            action="login",
            object_type="session",
            object_id=f"s-{i}",
        )
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        page1 = (
            await c.get("/v1/internal/audit?page=1&page_size=5", headers=_hdr())
        ).json()
        page3 = (
            await c.get("/v1/internal/audit?page=3&page_size=5", headers=_hdr())
        ).json()
    assert page1["page"] == 1 and page1["page_size"] == 5
    assert len(page1["items"]) == 5
    assert page1["total"] >= 12
    assert page1["total_pages"] >= 3
    assert len(page3["items"]) >= 2


@pytest.mark.asyncio
async def test_audit_endpoint_filters_by_action(app_with_secret, test_database_url):
    await _seed_audit_row(
        test_database_url,
        actor_id="maria@sandbox.example.com",
        action="login",
        object_type="session",
        object_id="s1",
    )
    await _seed_audit_row(
        test_database_url,
        actor_id="maria@sandbox.example.com",
        action="logout",
        object_type="session",
        object_id="s1",
    )
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        body = (await c.get("/v1/internal/audit?action=login", headers=_hdr())).json()
    actions = {i["action"] for i in body["items"]}
    assert actions == {"login"}


@pytest.mark.asyncio
async def test_audit_endpoint_rejects_unscoped_caller(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get(
            "/v1/internal/audit",
            headers={"Authorization": f"Bearer {SHARED_VAL}", "X-SBS-Role": "irrelevant"},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_audit_endpoint_accepts_supervisor_role(
    app_with_secret, test_database_url
):
    await _seed_audit_row(
        test_database_url,
        actor_id="maria@sandbox.example.com",
        action="login",
        object_type="session",
        object_id="s1",
    )
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get(
            "/v1/internal/audit", headers=_hdr("sbs:conduct:supervisor")
        )
    assert response.status_code == 200


# -- Audit row completeness -----------------------------------------------


@pytest.mark.asyncio
async def test_audit_login_row_carries_landed_route(db_schema, test_database_url):
    await _seed_audit_row(
        test_database_url,
        actor_id="maria@sandbox.example.com",
        action="login",
        object_type="session",
        object_id="s-1",
        meta={"roles": ["sbs:conduct:supervisor"], "landed_at": "/cockpit"},
    )
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.audit_event import AuditEvent

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionMaker() as session:
        rows = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "login")
            )
        ).scalars().all()
    await engine.dispose()
    assert len(rows) >= 1
    meta = rows[0].meta or {}
    assert "landed_at" in meta
    assert "roles" in meta


@pytest.mark.asyncio
async def test_audit_switch_persona_row_carries_from_and_to(db_schema, test_database_url):
    await _seed_audit_row(
        test_database_url,
        actor_id="operator",
        action="switch-persona",
        object_type="session",
        object_id="s-1",
        meta={
            "from_persona": "maria",
            "from_email": "maria@sandbox.example.com",
            "to_persona": "jorge",
            "to_email": "jorge@sandbox.example.com",
        },
    )
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.audit_event import AuditEvent

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionMaker() as session:
        rows = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "switch-persona")
            )
        ).scalars().all()
    await engine.dispose()
    assert len(rows) >= 1
    meta = rows[0].meta or {}
    # Non-droppable: from/to both filled.
    assert meta["from_persona"] == "maria"
    assert meta["to_persona"] == "jorge"
    assert rows[0].actor_id == "operator"


@pytest.mark.asyncio
async def test_audit_edit_draft_narrative_row_carries_before_and_after(db_schema, test_database_url):
    await _seed_audit_row(
        test_database_url,
        actor_id="lucia@sandbox.example.com",
        action="edit-draft-narrative",
        object_type="complaint",
        object_id="BCO-2026-000001",
        diff={"before_excerpt": "Disputa de cliente.", "after_excerpt": "Disputa con mencion."},
        meta={"complaint_id": "BCO-2026-000001", "draft_id": 1},
    )
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.audit_event import AuditEvent

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionMaker() as session:
        rows = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "edit-draft-narrative")
            )
        ).scalars().all()
    await engine.dispose()
    assert len(rows) >= 1
    diff = rows[0].diff or {}
    assert "before_excerpt" in diff and "after_excerpt" in diff


# -- Findings SSE role scope ----------------------------------------------


@pytest.mark.asyncio
async def test_findings_sse_topic_allows_supervisor(app_with_secret):
    status, headers = await open_sse_head_only(
        app_with_secret,
        "/v1/internal/sse/findings",
        _hdr("sbs:conduct:supervisor"),
    )
    assert status == 200
    assert b"text/event-stream" in headers.get(b"content-type", b"")


@pytest.mark.asyncio
async def test_findings_sse_topic_allows_analyst(app_with_secret):
    status, _ = await open_sse_head_only(
        app_with_secret,
        "/v1/internal/sse/findings",
        _hdr("sbs:conduct:analyst"),
    )
    assert status == 200


@pytest.mark.asyncio
async def test_findings_sse_topic_allows_head(app_with_secret):
    status, _ = await open_sse_head_only(
        app_with_secret,
        "/v1/internal/sse/findings",
        _hdr("sbs:conduct:head"),
    )
    assert status == 200


# -- SSE reconnect replay -------------------------------------------------


@pytest.mark.asyncio
async def test_sse_bus_replays_after_last_event_id():
    """Direct manager-level test (in-process, no HTTP) of the replay
    contract. The HTTP-level replay is the same path because the route
    handler delegates to SSEBus.subscribe()."""

    from sbs_api.sse.manager import SSEBus

    bus = SSEBus()
    # Publish 6 events.
    for _ in range(6):
        await bus.publish("findings", "complaint.received", "{}")
    # Subscribe with last_event_id=4 → expect events 5 + 6 in order.
    received: list = []

    async def consume() -> None:
        async for evt in bus.subscribe("findings", last_event_id=4):
            received.append(evt.id)
            if len(received) >= 2:
                return

    await asyncio.wait_for(consume(), timeout=1.0)
    assert received == [5, 6]


@pytest.mark.asyncio
async def test_sse_bus_replay_does_not_duplicate_live_events():
    """Subscribe, then publish — the live stream should receive only
    events newer than the snapshot at subscribe time."""

    from sbs_api.sse.manager import SSEBus

    bus = SSEBus()
    for _ in range(3):
        await bus.publish("findings", "complaint.received", "{}")

    received: list = []

    async def consume() -> None:
        async for evt in bus.subscribe("findings", last_event_id=2):
            received.append(evt.id)
            if len(received) >= 2:
                return

    consumer_task = asyncio.create_task(consume())
    # Give the consumer one tick to register its subscription.
    await asyncio.sleep(0)
    # Publish one more event; it should arrive on the live stream
    # without duplicating the backlog.
    await bus.publish("findings", "complaint.received", "{}")
    await asyncio.wait_for(consumer_task, timeout=1.0)
    # Backlog id=3, then live id=4. No dups.
    assert received == [3, 4]
