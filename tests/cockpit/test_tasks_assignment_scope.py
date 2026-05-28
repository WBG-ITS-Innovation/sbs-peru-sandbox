"""Task transitions are callable only by the assigned persona (P-RESHAPE-8.5)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.cockpit.conftest import hdr
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

_R30 = "Profundizar en este patrón de fraude emergente del sector."


async def _new_deeper_look(c: AsyncClient) -> str:
    r = await c.post(
        "/v1/internal/exec/tasking",
        json={"actor_user_id": "sergio", "ref_id": "pat-1", "rationale": _R30},
        headers=hdr("sbs:superintendent"),
    )
    assert r.status_code == 201
    return r.json()["task_id"]


@pytest.mark.asyncio
async def test_assigned_persona_can_ack(secret_app):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        task_id = await _new_deeper_look(c)
        r = await c.post(
            f"/v1/internal/cockpit/tasks/{task_id}/ack",
            json={"actor_user_id": "jorge"},
            headers=hdr("sbs:conduct:head"),
        )
    assert r.status_code == 200
    assert r.json()["state"] == "ACKED"


@pytest.mark.asyncio
async def test_wrong_persona_cannot_ack(secret_app):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        task_id = await _new_deeper_look(c)
        r = await c.post(
            f"/v1/internal/cockpit/tasks/{task_id}/ack",
            json={"actor_user_id": "lucia"},
            headers=hdr("sbs:conduct:analyst"),
        )
    assert r.status_code == 403  # analyst is neither the persona nor the named user


@pytest.mark.asyncio
async def test_complete_by_assigned_persona(secret_app):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        task_id = await _new_deeper_look(c)
        r = await c.post(
            f"/v1/internal/cockpit/tasks/{task_id}/complete",
            json={"actor_user_id": "jorge", "response": "Revisado."},
            headers=hdr("sbs:conduct:head"),
        )
    assert r.status_code == 200
    assert r.json()["state"] == "COMPLETED"


@pytest.mark.asyncio
async def test_decline_requires_30_char_rationale(secret_app):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        task_id = await _new_deeper_look(c)
        short = await c.post(
            f"/v1/internal/cockpit/tasks/{task_id}/decline",
            json={"actor_user_id": "jorge", "rationale": "no"},
            headers=hdr("sbs:conduct:head"),
        )
        assert short.status_code == 422
        ok = await c.post(
            f"/v1/internal/cockpit/tasks/{task_id}/decline",
            json={
                "actor_user_id": "jorge",
                "rationale": "No procede ahora; revisar en el próximo ciclo trimestral.",
            },
            headers=hdr("sbs:conduct:head"),
        )
    assert ok.status_code == 200
    assert ok.json()["state"] == "DECLINED"


@pytest.mark.asyncio
async def test_ack_unknown_task_404(secret_app):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            "/v1/internal/cockpit/tasks/does-not-exist/ack",
            json={"actor_user_id": "jorge"},
            headers=hdr("sbs:conduct:head"),
        )
    assert r.status_code == 404
