"""Persona action endpoints — persist + scope + rationale (P-RESHAPE-8.5)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.db.models.digest_audit import DigestAudit
from sbs_api.db.models.manual_finding import ManualFinding
from sbs_api.db.models.persona_task import PersonaTask
from tests.cockpit.conftest import hdr
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

_RATIONALE_30 = "Patrón sostenido de cobros indebidos en la cohorte."  # >= 30
_RATIONALE_20 = "Revisar este reclamo."  # >= 20 chars


async def _count(test_database_url, model) -> int:
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            return (
                await session.execute(select(func.count()).select_from(model))
            ).scalar_one()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_propose_pattern_creates_manual_finding(secret_app, test_database_url):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            "/v1/internal/findings/manual",
            json={
                "proposed_by_user_id": "lucia",
                "summary": "Posible patrón no detectado en COBRO_INDEBIDO.",
                "rationale": _RATIONALE_30,
            },
            headers=hdr("sbs:conduct:analyst"),
        )
    assert r.status_code == 201
    assert r.json()["status"] == "PROPOSED"
    assert await _count(test_database_url, ManualFinding) == 1


@pytest.mark.asyncio
async def test_propose_pattern_short_rationale_422(secret_app, test_database_url):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            "/v1/internal/findings/manual",
            json={
                "proposed_by_user_id": "lucia",
                "summary": "x",
                "rationale": "too short",
            },
            headers=hdr("sbs:conduct:analyst"),
        )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_request_deeper_look_creates_task(secret_app, test_database_url):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            "/v1/internal/exec/tasking",
            json={
                "actor_user_id": "sergio",
                "ref_type": "PATTERN",
                "ref_id": "pat-1",
                "rationale": _RATIONALE_30,
            },
            headers=hdr("sbs:superintendent"),
        )
    assert r.status_code == 201
    assert r.json()["task_type"] == "DEEPER_LOOK"
    assert await _count(test_database_url, PersonaTask) == 1


@pytest.mark.asyncio
async def test_digest_generate_then_acknowledge(secret_app, test_database_url):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        gen = await c.post(
            "/v1/internal/exec/digest/generate",
            json={"actor_user_id": "jorge", "summary": "Resumen semanal."},
            headers=hdr("sbs:conduct:head"),
        )
        assert gen.status_code == 201
        digest_id = gen.json()["digest_id"]
        ack = await c.post(
            f"/v1/internal/exec/digest/{digest_id}/acknowledge",
            json={"actor_user_id": "sergio"},
            headers=hdr("sbs:superintendent"),
        )
    assert ack.status_code == 201
    # Two digest_audit rows: GENERATED + ACKNOWLEDGED.
    assert await _count(test_database_url, DigestAudit) == 2


@pytest.mark.asyncio
async def test_annotate_incident_no_business_fields(secret_app, test_database_url):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            "/v1/internal/ops/incidents",
            json={
                "actor_user_id": "rosa",
                "component": "webhook_delivery",
                "severity": "AMBER",
                "note": "Entrega de webhooks degradada 10:00-10:20.",
            },
            headers=hdr("sbs:sbs_it"),
        )
    assert r.status_code == 201
    body = r.json()
    assert body["component"] == "webhook_delivery"
    assert "complaint_id" not in body


@pytest.mark.asyncio
async def test_superintendent_cannot_propose_pattern(secret_app):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            "/v1/internal/findings/manual",
            json={
                "proposed_by_user_id": "sergio",
                "summary": "x",
                "rationale": _RATIONALE_30,
            },
            headers=hdr("sbs:superintendent"),
        )
    assert r.status_code == 403  # lacks findings:propose


@pytest.mark.asyncio
async def test_analyst_cannot_generate_digest(secret_app):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            "/v1/internal/exec/digest/generate",
            json={"actor_user_id": "lucia"},
            headers=hdr("sbs:conduct:analyst"),
        )
    assert r.status_code == 403  # lacks digest:generate
