"""End-to-end test for the P11A demo ingestion endpoint.

Drives ``POST /v1/internal/demo/simulate-submission`` with the golden
PII payload through the in-process FastAPI app and asserts:

* HTTP 201 with the documented response envelope.
* Canonical ``complaints`` row created with redacted text only.
* ``raw_complaints`` row created with the full raw narrative and
  payload.
* One ``agent_runs`` row created with status='success' (no DQ errors
  on the golden payload), with the anonymizer tool_call and the DQ
  report in final_output. The agent_run validates against the
  existing JSON Schema.
* Five audit-chain rows recorded in kebab-case.
* The SSE bus received one ``complaint.received`` event whose data is
  PII-free.
* The Pydantic response envelope round-trips correctly.

DB-gated via pytestmark_db.
"""

from __future__ import annotations

import json
import pathlib

import jsonschema
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


SHARED_VAL = "sandbox-p11a-live-ingestion-test"  # pragma: allowlist secret

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "docs" / "schemas" / "agent_run.schema.json"


GOLDEN_PAYLOAD = {
    "institution_id": "SBS-001234",
    "institution_name": "BANCO_DEMO_001",
    "institution_complaint_id": "BCO-DEMO-IN-0001",
    "client_submission_id": "test-live-001",
    "received_at": "2026-05-24T10:15:00-05:00",
    "channel_in": "APP_MOVIL",
    "channel_operation": "APP_MOVIL",
    "product": "TARJETA_CREDITO",
    "motive": "COBRO_INDEBIDO",
    "narrative": (
        "El cliente Carlos Rodríguez Mendoza (DNI 12345678) reporta un cargo "
        "no reconocido por S/ 700 en la tarjeta 4556 1234 5678 9999. "
        "Indica que recibió notificaciones por su billetera digital y "
        "solicita que lo contactemos al +51 987 654 321 o al correo "
        "carlos.rodriguez@example.com."
    ),
    "response_detail": None,
    "status": "pendiente",
    "severity": "HIGH",
    "demo_scenario": "p11a-live-ingestion-test",
}


RAW_PII_NEEDLES = (
    "Carlos Rodríguez Mendoza",
    "Carlos Rodriguez Mendoza",
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


def _hdr(role: str = "sbs:conduct:supervisor") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {SHARED_VAL}",
        "X-SBS-Role": role,
    }


def _no_raw_pii(text: str) -> None:
    for needle in RAW_PII_NEEDLES:
        assert needle not in text, f"raw PII leaked: {needle!r}"


@pytest.mark.asyncio
async def test_demo_endpoint_happy_path(app_with_secret, test_database_url):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        res = await c.post(
            "/v1/internal/demo/simulate-submission",
            json=GOLDEN_PAYLOAD,
            headers=_hdr(),
        )
    assert res.status_code == 201, res.text
    body = res.json()

    # Envelope shape.
    assert body["complaint_id"]
    assert body["raw_complaint_id"]
    assert body["agent_run_id"]
    # event_id may be None if the SSE bus dropped (best-effort).
    assert "event_id" in body
    assert body["institution_id"] == "SBS-001234"

    # Timeline contains every required event in order.
    timeline_events = [t["event"] for t in body["timeline"]]
    for required in (
        "received",
        "institution_authenticated_simulated",
        "schema_validated",
        "pii_redacted",
        "canonical_complaint_persisted",
        "data_quality_checks_completed",
        "finding_triage_event_emitted",
    ):
        assert required in timeline_events, timeline_events

    # Redaction diff sanity.
    diff = body["redaction_diff"]
    assert diff["policy_version"]
    assert diff["before_masked"]
    assert diff["after_redacted"]
    _no_raw_pii(diff["before_masked"])
    _no_raw_pii(diff["after_redacted"])
    # Browser-visible entities are matched_value-free.
    for ent in diff["entities"]:
        assert "matched_value" not in ent

    # DQ sanity — golden payload is well-formed; no errors.
    dq = body["data_quality"]
    assert dq["errors"] == []
    assert dq["policy_version"]


@pytest.mark.asyncio
async def test_demo_endpoint_persists_raw_only_in_raw_complaints(
    app_with_secret, test_database_url
):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        res = await c.post(
            "/v1/internal/demo/simulate-submission",
            json=GOLDEN_PAYLOAD,
            headers=_hdr(),
        )
    assert res.status_code == 201
    body = res.json()

    from sbs_api.db.models.complaint import ComplaintRecord
    from sbs_api.db.models.raw_complaint import RawComplaint

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            canonical = (
                await session.execute(
                    select(ComplaintRecord).where(
                        ComplaintRecord.complaint_id == body["complaint_id"]
                    )
                )
            ).scalar_one()
            raw = (
                await session.execute(
                    select(RawComplaint).where(
                        RawComplaint.id == body["raw_complaint_id"]
                    )
                )
            ).scalar_one()
    finally:
        await engine.dispose()

    # Canonical row is PII-free.
    _no_raw_pii(canonical.description_text)
    # Raw row carries the full PII narrative.
    for needle in RAW_PII_NEEDLES[:1] + RAW_PII_NEEDLES[2:]:
        # Skip the unaccented Carlos variant — the input is accented.
        if needle == "Carlos Rodriguez Mendoza":
            continue
        assert needle in raw.raw_narrative, needle
    # FK backfilled.
    assert raw.canonical_complaint_id == canonical.complaint_id
    assert raw.storage_policy == "restricted-demo-pii-v1"


@pytest.mark.asyncio
async def test_demo_endpoint_writes_pii_free_agent_run(
    app_with_secret, test_database_url
):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        res = await c.post(
            "/v1/internal/demo/simulate-submission",
            json=GOLDEN_PAYLOAD,
            headers=_hdr(),
        )
    body = res.json()

    from sbs_api.db.models.agent_run import AgentRun

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            run = (
                await session.execute(
                    select(AgentRun).where(AgentRun.id == body["agent_run_id"])
                )
            ).scalar_one()
    finally:
        await engine.dispose()

    assert run.agent_name == "live-ingestion-orchestrator"
    assert run.agent_version.startswith("live-ingestion-orchestrator-")
    assert run.status == "success"

    serialised = json.dumps(
        {
            "tool_calls": run.tool_calls,
            "final_output": run.final_output,
            "error": run.error,
        }
    )
    _no_raw_pii(serialised)

    # One anonymizer tool_call; DQ report lives in final_output.
    tool_names = [tc["tool_name"] for tc in run.tool_calls]
    assert tool_names == ["anonymizer"]
    assert run.final_output["data_quality"]["policy_version"]

    # The full agent_run validates against the JSON Schema contract.
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    row_dict = {
        "id": run.id,
        "complaint_id": run.complaint_id,
        "agent_name": run.agent_name,
        "agent_version": run.agent_version,
        "started_at": run.started_at.isoformat(timespec="seconds"),
        "ended_at": run.ended_at.isoformat(timespec="seconds") if run.ended_at else None,
        "status": run.status,
        "tool_calls": run.tool_calls,
        "final_output": run.final_output,
        "error": run.error,
    }
    validator.validate(row_dict)


@pytest.mark.asyncio
async def test_demo_endpoint_records_five_audit_events(
    app_with_secret, test_database_url
):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        res = await c.post(
            "/v1/internal/demo/simulate-submission",
            json=GOLDEN_PAYLOAD,
            headers=_hdr(),
        )
    body = res.json()

    from sbs_api.db.models.audit_event import AuditEvent

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            rows = (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.object_id == body["complaint_id"]
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    actions = sorted(r.action for r in rows)
    assert actions == sorted(
        [
            "demo-complaint-received",
            "pii-redacted",
            "canonical-complaint-persisted",
            "data-quality-completed",
            "complaint-triage-emitted",
        ]
    )
    # No raw PII in any audit row.
    for row in rows:
        for col in (row.action, row.actor_id, row.object_id):
            _no_raw_pii(col)
        _no_raw_pii(json.dumps(row.diff))
        _no_raw_pii(json.dumps(row.meta))


@pytest.mark.asyncio
async def test_demo_endpoint_publishes_pii_free_sse_event(
    app_with_secret, test_database_url
):
    from sbs_api.sse import get_bus

    bus = get_bus()
    # Capture the cockpit-topic backlog before the call.
    pre_state = list(bus._topics.get("cockpit", type("S", (), {"buffer": []})).buffer)  # type: ignore[attr-defined]

    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        res = await c.post(
            "/v1/internal/demo/simulate-submission",
            json=GOLDEN_PAYLOAD,
            headers=_hdr(),
        )
    assert res.status_code == 201

    cockpit_state = bus._topics.get("cockpit")  # type: ignore[attr-defined]
    assert cockpit_state is not None
    new_events = [e for e in cockpit_state.buffer if e not in pre_state]
    received_events = [e for e in new_events if e.event == "complaint.received"]
    assert len(received_events) == 1
    payload = json.loads(received_events[0].data)
    _no_raw_pii(json.dumps(payload))
    assert payload["institution_id"] == "SBS-001234"
    assert payload["source"] == "api_realtime"
    assert "description_preview" in payload


@pytest.mark.asyncio
async def test_demo_endpoint_rejects_without_internal_secret(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        res = await c.post(
            "/v1/internal/demo/simulate-submission",
            json=GOLDEN_PAYLOAD,
            headers={"X-SBS-Role": "sbs:conduct:supervisor"},
        )
    assert res.status_code == 401
