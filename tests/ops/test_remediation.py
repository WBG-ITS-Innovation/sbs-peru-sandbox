"""IT remediation endpoints (P-RESHAPE-9).

Rosa (sbs_it) can retry a failed webhook, requeue a failed agent run, and
PAUSE/RESUME a circuit breaker. Jorge (conduct head) is denied. Each
action lands an incident_annotations audit row.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.db.models.incident_annotation import IncidentAnnotation
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

_R20 = "Reintento manual tras incidente de red."
_R50 = "Incidente grave en BANCO_DEMO_001: pausamos la ingestión mientras se investiga."


def _rosa():
    return {"Authorization": "Bearer stub:rosa"}


def _jorge():
    return {"Authorization": "Bearer stub:jorge"}


async def _seed_failed_webhook(test_database_url: str) -> str:
    from sbs_api.db.models.batch import BatchRecord
    from sbs_api.db.models.webhook_delivery import WebhookDelivery

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    delivery_id = f"wd_{uuid.uuid4().hex[:20]}"
    batch_id = f"batch_{uuid.uuid4().hex[:20]}"
    async with SM() as session:
        session.add(
            BatchRecord(
                batch_id=batch_id,
                institution_id="SBS-001234",
                file_name="b.csv",
                reporting_period_start=date(2026, 5, 1),
                reporting_period_end=date(2026, 5, 31),
                schema_version="v0.1.0",
                row_count_submitted=1,
                sha256="0" * 64,
                status="complete",
            )
        )
        await session.flush()
        session.add(
            WebhookDelivery(
                delivery_id=delivery_id,
                batch_id=batch_id,
                institution_id="SBS-001234",
                event_type="batch.completed",
                payload="{}",
                status="delivery_failed",
                attempts=5,
            )
        )
        await session.commit()
    await engine.dispose()
    return delivery_id


async def _seed_failed_run(test_database_url: str) -> str:
    from sbs_api.db.models.agent_run import AgentRun

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    run_id = str(uuid.uuid4())
    async with SM() as session:
        session.add(
            AgentRun(
                id=run_id,
                complaint_id="BCO-2026-000001",
                agent_name="investigation",
                agent_version="investigation-0.1.0",
                started_at=datetime.now(tz=timezone.utc),
                ended_at=datetime.now(tz=timezone.utc),
                status="failed",
                tool_calls=[],
                final_output=None,
                error={"code": "boom"},
            )
        )
        await session.commit()
    await engine.dispose()
    return run_id


async def _annotation_count(test_database_url: str) -> int:
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            return (
                await session.execute(
                    select(func.count()).select_from(IncidentAnnotation)
                )
            ).scalar_one()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rosa_retry_webhook(stub_app, test_database_url):
    delivery_id = await _seed_failed_webhook(test_database_url)
    transport = ASGITransport(app=stub_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            f"/v1/internal/ops/webhooks/{delivery_id}/retry",
            json={"actor_user_id": "rosa", "rationale": _R20},
            headers=_rosa(),
        )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"
    assert r.json()["attempts"] == 6
    assert await _annotation_count(test_database_url) == 1


@pytest.mark.asyncio
async def test_rosa_requeue_agent_run(stub_app, test_database_url):
    run_id = await _seed_failed_run(test_database_url)
    transport = ASGITransport(app=stub_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            f"/v1/internal/ops/runs/{run_id}/requeue",
            json={"actor_user_id": "rosa", "rationale": _R20},
            headers=_rosa(),
        )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "in_progress"
    assert r.json()["new_run_id"] != run_id


@pytest.mark.asyncio
async def test_rosa_circuit_breaker_pause_resume(stub_app, test_database_url):
    transport = ASGITransport(app=stub_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        pause = await c.post(
            "/v1/internal/ops/circuit_breaker/SBS-001234",
            json={"actor_user_id": "rosa", "action": "PAUSE", "rationale": _R50},
            headers=_rosa(),
        )
        assert pause.status_code == 200, pause.text
        assert pause.json()["state"] == "PAUSED"
        resume = await c.post(
            "/v1/internal/ops/circuit_breaker/SBS-001234",
            json={"actor_user_id": "rosa", "action": "RESUME", "rationale": _R50},
            headers=_rosa(),
        )
    assert resume.json()["state"] == "NORMAL"


@pytest.mark.asyncio
async def test_circuit_breaker_requires_50_char_rationale(stub_app):
    transport = ASGITransport(app=stub_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            "/v1/internal/ops/circuit_breaker/SBS-001234",
            json={"actor_user_id": "rosa", "action": "PAUSE", "rationale": "too short"},
            headers=_rosa(),
        )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_jorge_denied_remediation(stub_app, test_database_url):
    delivery_id = await _seed_failed_webhook(test_database_url)
    transport = ASGITransport(app=stub_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            f"/v1/internal/ops/webhooks/{delivery_id}/retry",
            json={"actor_user_id": "jorge", "rationale": _R20},
            headers=_jorge(),
        )
    assert r.status_code == 403  # conduct head lacks ops:remediate
