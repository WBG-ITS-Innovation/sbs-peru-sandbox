"""Architectural invariant test: raw PII lives only in raw_complaints.

The P11A demo path is the **only** code surface that accepts raw PII.
The contract from ADR 0044 is:

* Raw narrative + raw payload → ``raw_complaints`` only.
* Canonical ``complaints``, ``agent_runs``, ``audit_events``, SSE
  payloads, and the HTTP response envelope carry only redacted text.

This test drives the demo endpoint with the golden payload and
asserts the invariant against the on-disk state of every table that
is expected to be PII-free.
"""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


SHARED_VAL = "sandbox-p11a-no-pii-egress-test"  # pragma: allowlist secret

GOLDEN_PAYLOAD = {
    "institution_id": "SBS-001234",
    "institution_name": "BANCO_DEMO_001",
    "institution_complaint_id": "BCO-DEMO-IN-0002",
    "client_submission_id": "test-no-pii-egress",
    # P11 DQ completion — Annex 1-A fields 2 + 3.
    "tid_cli": "DNI",
    "nro_cli": "12345678",
    "received_at": "2026-05-24T10:15:00-05:00",
    "channel_in": "APP_MOVIL",
    "channel_operation": "APP_MOVIL",
    "product": "TARJETA_CREDITO",
    "motive": "COBRO_INDEBIDO",
    "narrative": (
        "El cliente Carlos Rodríguez Mendoza (DNI 12345678) reporta un cargo "
        "no reconocido por S/ 700 en la tarjeta 4556 1234 5678 9999. "
        "Lo pueden contactar al +51 987 654 321 o al correo "
        "carlos.rodriguez@example.com."
    ),
    "response_detail": None,
    "status": "pendiente",
    "severity": "HIGH",
    "demo_scenario": "no-pii-egress",
}

RAW_PII_NEEDLES = (
    "Carlos Rodríguez Mendoza",
    "12345678",
    "987 654 321",
    "carlos.rodriguez@example.com",
    "4556 1234 5678 9999",
)


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


def _assert_no_pii(blob: str, where: str) -> None:
    for needle in RAW_PII_NEEDLES:
        assert needle not in blob, f"raw PII {needle!r} leaked into {where}"


@pytest.mark.asyncio
async def test_raw_pii_lives_only_in_raw_complaints(app_with_secret, test_database_url):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        res = await c.post(
            "/v1/internal/demo/simulate-submission",
            json=GOLDEN_PAYLOAD,
            headers={
                "Authorization": f"Bearer {SHARED_VAL}",
                "X-SBS-Role": "sbs:conduct:supervisor",
            },
        )
    assert res.status_code == 201, res.text

    # 1. Response body — no raw PII.
    _assert_no_pii(res.text, "HTTP response body")

    # 2. Database surfaces.
    from sbs_api.db.models.agent_run import AgentRun
    from sbs_api.db.models.audit_event import AuditEvent
    from sbs_api.db.models.complaint import ComplaintRecord
    from sbs_api.db.models.raw_complaint import RawComplaint

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            complaints = (await session.execute(select(ComplaintRecord))).scalars().all()
            runs = (await session.execute(select(AgentRun))).scalars().all()
            events = (await session.execute(select(AuditEvent))).scalars().all()
            raws = (await session.execute(select(RawComplaint))).scalars().all()
    finally:
        await engine.dispose()

    for c in complaints:
        _assert_no_pii(c.description_text or "", f"complaints.description_text [{c.complaint_id}]")
    for r in runs:
        blob = json.dumps(
            {
                "tool_calls": r.tool_calls,
                "final_output": r.final_output,
                "error": r.error,
            }
        )
        _assert_no_pii(blob, f"agent_runs row {r.id}")
    for e in events:
        blob = json.dumps(
            {
                "action": e.action,
                "actor_id": e.actor_id,
                "object_id": e.object_id,
                "diff": e.diff,
                "meta": e.meta,
            }
        )
        _assert_no_pii(blob, f"audit_events row {e.id}")

    # 3. raw_complaints should hold the raw narrative for THIS submission.
    assert any("Carlos Rodríguez Mendoza" in r.raw_narrative for r in raws), (
        "raw narrative not found in raw_complaints — the demo endpoint "
        "must persist raw PII somewhere"
    )


@pytest.mark.asyncio
async def test_sse_payload_published_is_pii_free(app_with_secret, test_database_url):
    from sbs_api.sse import get_bus

    bus = get_bus()
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        res = await c.post(
            "/v1/internal/demo/simulate-submission",
            json=GOLDEN_PAYLOAD,
            headers={
                "Authorization": f"Bearer {SHARED_VAL}",
                "X-SBS-Role": "sbs:conduct:supervisor",
            },
        )
    assert res.status_code == 201

    cockpit_state = bus._topics.get("cockpit")  # type: ignore[attr-defined]
    assert cockpit_state is not None
    for evt in cockpit_state.buffer:
        _assert_no_pii(evt.data, f"SSE event id={evt.id}")
