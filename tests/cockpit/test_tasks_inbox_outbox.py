"""Task inbox/outbox routing (P-RESHAPE-8.5).

Inbox returns user-targeted AND persona-targeted tasks; outbox returns
only tasks the caller created.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.cockpit.conftest import hdr
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

_R30 = "Revisión a nivel de reclamos individuales, por favor."


async def _seed_two_tasks(c: AsyncClient) -> None:
    # Supervisor delegates to a named analyst (lucia).
    d = await c.post(
        "/v1/internal/findings/find-1/delegate",
        json={"actor_user_id": "maria", "assigned_to_user_id": "lucia", "rationale": _R30},
        headers=hdr("sbs:conduct:supervisor"),
    )
    assert d.status_code == 201
    # Superintendent tasks the unit-head persona (no named user).
    t = await c.post(
        "/v1/internal/exec/tasking",
        json={"actor_user_id": "sergio", "ref_id": "pat-1", "rationale": _R30},
        headers=hdr("sbs:superintendent"),
    )
    assert t.status_code == 201


@pytest.mark.asyncio
async def test_inbox_user_targeted(secret_app):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await _seed_two_tasks(c)
        r = await c.get(
            "/v1/internal/cockpit/tasks/inbox",
            params={"user_id": "lucia"},
            headers=hdr("sbs:conduct:analyst"),
        )
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i["task_type"] == "PATTERN_DELEGATION" for i in items)


@pytest.mark.asyncio
async def test_inbox_persona_targeted(secret_app):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await _seed_two_tasks(c)
        # Jorge (unit head) sees the persona-targeted DEEPER_LOOK even
        # though it names no specific user.
        r = await c.get(
            "/v1/internal/cockpit/tasks/inbox",
            params={"user_id": "jorge"},
            headers=hdr("sbs:conduct:head"),
        )
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(i["task_type"] == "DEEPER_LOOK" for i in items)


@pytest.mark.asyncio
async def test_inbox_scoped_excludes_other_personas(secret_app):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await _seed_two_tasks(c)
        # A supervisor named "carlos" has no user-targeted task and no
        # supervisor-targeted task → empty inbox.
        r = await c.get(
            "/v1/internal/cockpit/tasks/inbox",
            params={"user_id": "carlos"},
            headers=hdr("sbs:conduct:supervisor"),
        )
    assert r.status_code == 200
    assert r.json()["total"] == 0


@pytest.mark.asyncio
async def test_outbox_returns_only_creator_tasks(secret_app):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await _seed_two_tasks(c)
        maria = await c.get(
            "/v1/internal/cockpit/tasks/outbox",
            params={"user_id": "maria"},
            headers=hdr("sbs:conduct:supervisor"),
        )
        sergio = await c.get(
            "/v1/internal/cockpit/tasks/outbox",
            params={"user_id": "sergio"},
            headers=hdr("sbs:superintendent"),
        )
    assert {i["task_type"] for i in maria.json()["items"]} == {"PATTERN_DELEGATION"}
    assert {i["task_type"] for i in sergio.json()["items"]} == {"DEEPER_LOOK"}
