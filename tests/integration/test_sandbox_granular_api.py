# SPDX-License-Identifier: Apache-2.0
"""End-to-end test for the P11A.5a sandbox granular institutional endpoint.

Drives ``POST /v1/sandbox/complaints/granular`` through the in-process
FastAPI app using the shared ``client`` fixture (which bypasses mTLS
/ OAuth / HMAC / rate-limit dependencies, mirroring the existing
``/v1/complaints`` test pattern). The HMAC chain is exercised by the
dedicated ``test_hmac_*.py`` files; this test covers the route's own
logic — orchestrator wiring, receipt shape, idempotency, tenant
binding, missing-auth fallthroughs, and the no-raw-PII egress
guarantee.
"""

from __future__ import annotations

import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


GRANULAR_PATH = "/v1/sandbox/complaints/granular"


GOLDEN_PAYLOAD = {
    "institution_id": "SBS-001234",
    "institution_name": "BANCO_DEMO_001",
    "institution_complaint_id": "BCO-CLI-IN-0001",
    "client_submission_id": "test-sandbox-001",
    # P11 DQ completion — Annex 1-A fields 2 + 3.
    "tid_cli": "DNI",
    "nro_cli": "47291834",
    "received_at": "2026-05-25T10:15:00-05:00",
    "channel_in": "APP_MOVIL",
    "channel_operation": "APP_MOVIL",
    "product": "TARJETA_CREDITO",
    "motive": "COBRO_INDEBIDO",
    "amount_claimed": "700.00",
    "narrative": (
        "El cliente Carlos Rodríguez Mendoza (DNI 12345678) reporta un cargo "
        "no reconocido por S/ 700 en la tarjeta 4556 1234 5678 9999. "
        "Indica que recibió notificaciones en el aplicativo móvil y "
        "solicita ser contactado al +51 987 654 321 o al correo "
        "carlos.rodriguez@example.com."
    ),
    "response_detail": None,
    "status": "pendiente",
    "severity": "HIGH",
    "demo_scenario": "p11a5a-sandbox-test",
}


RAW_PII_NEEDLES = (
    "Carlos Rodríguez Mendoza",
    "12345678",
    "987 654 321",
    "carlos.rodriguez@example.com",
    "4556 1234 5678 9999",
)


def _no_raw_pii(blob: str, where: str) -> None:
    for needle in RAW_PII_NEEDLES:
        assert needle not in blob, f"raw PII {needle!r} leaked into {where}"


def _idem_key(prefix: str) -> str:
    return f"sandbox-{prefix}-{uuid.uuid4().hex[:16]}"


# ---------------------------------------------------------------------------
# Happy path + receipt shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_granular_happy_path_returns_receipt(client):
    r = await client.post(
        GRANULAR_PATH,
        json=GOLDEN_PAYLOAD,
        headers={"Idempotency-Key": _idem_key("happy")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    # P11 DQ completion: the GOLDEN_PAYLOAD uses friendly-name channel
    # codes (APP_MOVIL) instead of the Anexo A numeric codes ("10");
    # DQ-A1A-013 surfaces this as a warning, so accepted_with_warnings
    # is also a valid happy-path outcome.
    assert body["status"] in ("accepted", "accepted_with_warnings"), body
    assert body["institution_id"] == "SBS-001234"
    assert body["complaint_id"]
    assert body["raw_complaint_id"]
    assert body["submission_id"]
    assert body["idempotency_key"]
    assert body["received_at"]
    assert body["redaction_policy_version"]
    assert body["data_quality_policy_version"]

    # Timeline contains the orchestrator's signature events.
    timeline_events = [t["event"] for t in body["timeline"]]
    for required in (
        "received",
        "pii_redacted",
        "canonical_complaint_persisted",
        "data_quality_checks_completed",
        "finding_triage_event_emitted",
    ):
        assert required in timeline_events, timeline_events

    # No raw PII in the response.
    _no_raw_pii(r.text, "HTTP response body")


@pytest.mark.asyncio
async def test_granular_response_has_no_raw_pii(client):
    r = await client.post(
        GRANULAR_PATH,
        json=GOLDEN_PAYLOAD,
        headers={"Idempotency-Key": _idem_key("no-pii")},
    )
    assert r.status_code == 201
    _no_raw_pii(r.text, "HTTP response body")


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_granular_idempotency_replay_returns_same_complaint(client):
    key = _idem_key("idem")
    r1 = await client.post(
        GRANULAR_PATH,
        json=GOLDEN_PAYLOAD,
        headers={"Idempotency-Key": key},
    )
    assert r1.status_code == 201
    cid1 = r1.json()["complaint_id"]

    r2 = await client.post(
        GRANULAR_PATH,
        json=GOLDEN_PAYLOAD,
        headers={"Idempotency-Key": key},
    )
    assert r2.status_code == 201
    cid2 = r2.json()["complaint_id"]
    # Same Idempotency-Key + same body → cached receipt with the
    # original complaint_id, not a fresh canonical complaint.
    assert cid1 == cid2
    assert r2.headers.get("Idempotency-Replayed") == "true"


@pytest.mark.asyncio
async def test_granular_idempotency_does_not_create_second_canonical_complaint(
    client, test_database_url
):
    from sbs_api.db.models.complaint import ComplaintRecord

    key = _idem_key("idem-count")
    payload = {**GOLDEN_PAYLOAD, "client_submission_id": "idem-count-test"}
    r1 = await client.post(
        GRANULAR_PATH, json=payload, headers={"Idempotency-Key": key}
    )
    assert r1.status_code == 201
    cid = r1.json()["complaint_id"]

    r2 = await client.post(
        GRANULAR_PATH, json=payload, headers={"Idempotency-Key": key}
    )
    assert r2.status_code == 201

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            rows = (
                await session.execute(
                    select(ComplaintRecord).where(
                        ComplaintRecord.client_submission_id == "idem-count-test"
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    assert len(rows) == 1, "idempotency replay created a duplicate canonical complaint"
    assert rows[0].complaint_id == cid


# ---------------------------------------------------------------------------
# Header / auth fallthroughs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_granular_requires_idempotency_key(client):
    r = await client.post(GRANULAR_PATH, json=GOLDEN_PAYLOAD)
    # FastAPI's required-header validation returns 422 (or 400 depending
    # on how the route declares it). Either way it must not 2xx.
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_granular_rejects_missing_oauth_bearer(app):
    """Pop the OAuth scope override so the route exercises the real dep."""

    from sbs_api.auth.scopes import COMPLAINTS_WRITE
    from sbs_api.dependencies.oauth import verified_oauth_token_with_scope

    dep = verified_oauth_token_with_scope(COMPLAINTS_WRITE)
    app.dependency_overrides.pop(dep, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        r = await ac.post(
            GRANULAR_PATH,
            json=GOLDEN_PAYLOAD,
            headers={"Idempotency-Key": _idem_key("no-oauth")},
        )
    assert r.status_code == 401
    body = r.json()
    # The OAuth dependency raises TokenRequired/Invalid, which surface
    # with a stable code from the catalogue.
    assert body.get("code", "").startswith("SBS-401-")


@pytest.mark.asyncio
async def test_granular_rejects_missing_hmac(app):
    """Pop the HMAC bypass so the route runs the real verifier."""

    from sbs_api.dependencies.hmac_verify import verified_hmac_signature

    app.dependency_overrides.pop(verified_hmac_signature, None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        r = await ac.post(
            GRANULAR_PATH,
            json=GOLDEN_PAYLOAD,
            headers={"Idempotency-Key": _idem_key("no-hmac")},
        )
    assert r.status_code == 401
    body = r.json()
    # Missing X-SBS-Timestamp / X-SBS-Signature surfaces as
    # SIGNATURE_MISSING_HEADER.
    assert "SIGNATURE_MISSING_HEADER" in body.get("type", "")


@pytest.mark.asyncio
async def test_granular_tenant_mismatch_returns_404(client):
    bad = {**GOLDEN_PAYLOAD, "institution_id": "SBS-005678"}
    r = await client.post(
        GRANULAR_PATH,
        json=bad,
        headers={"Idempotency-Key": _idem_key("tenant")},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# PII egress — DB surfaces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_granular_raw_pii_only_in_raw_complaints(client, test_database_url):
    r = await client.post(
        GRANULAR_PATH,
        json=GOLDEN_PAYLOAD,
        headers={"Idempotency-Key": _idem_key("egress")},
    )
    assert r.status_code == 201
    body = r.json()

    from sbs_api.db.models.agent_run import AgentRun
    from sbs_api.db.models.audit_event import AuditEvent
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
            run = (
                await session.execute(
                    select(AgentRun).where(AgentRun.id == body["submission_id"])
                )
            ).scalar_one()
            events = (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.object_id == body["complaint_id"]
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    _no_raw_pii(canonical.description_text, "complaints.description_text")
    run_blob = json.dumps(
        {
            "tool_calls": run.tool_calls,
            "final_output": run.final_output,
            "error": run.error,
        }
    )
    _no_raw_pii(run_blob, "agent_runs row")
    for ev in events:
        ev_blob = json.dumps(
            {
                "action": ev.action,
                "actor_id": ev.actor_id,
                "object_id": ev.object_id,
                "diff": ev.diff,
                "meta": ev.meta,
            }
        )
        _no_raw_pii(ev_blob, f"audit_events row {ev.id}")

    # Raw narrative present in raw_complaints.
    assert "Carlos Rodríguez Mendoza" in raw.raw_narrative
    assert raw.canonical_complaint_id == canonical.complaint_id


@pytest.mark.asyncio
async def test_granular_sse_payload_is_pii_free(client):
    from sbs_api.sse import get_bus

    bus = get_bus()
    pre = list(
        bus._topics.get("cockpit", type("S", (), {"buffer": []})).buffer  # type: ignore[attr-defined]
    )
    r = await client.post(
        GRANULAR_PATH,
        json=GOLDEN_PAYLOAD,
        headers={"Idempotency-Key": _idem_key("sse")},
    )
    assert r.status_code == 201

    cockpit_state = bus._topics.get("cockpit")  # type: ignore[attr-defined]
    assert cockpit_state is not None
    new_events = [e for e in cockpit_state.buffer if e not in pre]
    received = [e for e in new_events if e.event == "complaint.received"]
    assert received, "no complaint.received SSE event from sandbox endpoint"
    _no_raw_pii(received[-1].data, "SSE event data")


# ---------------------------------------------------------------------------
# P11 sandbox completion — exit-gate 1 anchor: a full Peruvian-PII payload
# (DNI + RUC + phone + email + Spanish name) must end up with raw PII in
# raw_complaints only; canonical complaint, SSE, audit, agent_run, and
# response body all carry redacted text exclusively.
# ---------------------------------------------------------------------------


P11_FULL_PII_NARRATIVE = (
    "El cliente Carlos Rodríguez Mendoza (DNI 47291834) representa a la "
    "empresa RUC 20512345678 y reporta un cargo no reconocido por S/ 450 "
    "en la tarjeta 4556 1234 5678 9999. Contactarlo al +51 987 654 321 o "
    "al correo carlos.rodriguez@example.com."
)

P11_FULL_PII_NEEDLES = (
    "Carlos Rodríguez Mendoza",
    "47291834",
    "20512345678",
    "987 654 321",
    "carlos.rodriguez@example.com",
    "4556 1234 5678 9999",
)


@pytest.mark.asyncio
async def test_granular_full_peruvian_pii_payload_egress(client, test_database_url):
    """Exit gate 1+2: DNI/RUC/phone/email/name all redacted before
    canonical storage. raw_complaints holds the raw narrative; every
    other surface is PII-free."""

    payload = {
        **GOLDEN_PAYLOAD,
        "client_submission_id": "p11-full-pii-egress",
        "narrative": P11_FULL_PII_NARRATIVE,
        "demo_scenario": "p11-sandbox-close",
    }
    r = await client.post(
        GRANULAR_PATH,
        json=payload,
        headers={"Idempotency-Key": _idem_key("full-pii")},
    )
    assert r.status_code == 201, r.text
    body = r.json()

    # Response body: no raw PII.
    for needle in P11_FULL_PII_NEEDLES:
        assert needle not in r.text, f"raw PII {needle!r} leaked into response"

    # DB surfaces.
    from sbs_api.db.models.agent_run import AgentRun
    from sbs_api.db.models.audit_event import AuditEvent
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
            run = (
                await session.execute(
                    select(AgentRun).where(AgentRun.id == body["submission_id"])
                )
            ).scalar_one()
            events = (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.object_id == body["complaint_id"]
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    # Canonical complaint: no raw PII at all.
    for needle in P11_FULL_PII_NEEDLES:
        assert needle not in (canonical.description_text or ""), (
            f"raw PII {needle!r} leaked into canonical complaint"
        )
    # agent_run + audit: same.
    run_blob = json.dumps(
        {"tool_calls": run.tool_calls, "final_output": run.final_output, "error": run.error}
    )
    for needle in P11_FULL_PII_NEEDLES:
        assert needle not in run_blob, f"raw PII {needle!r} leaked into agent_run"
    for ev in events:
        ev_blob = json.dumps(
            {"action": ev.action, "actor_id": ev.actor_id, "object_id": ev.object_id,
             "diff": ev.diff, "meta": ev.meta}
        )
        for needle in P11_FULL_PII_NEEDLES:
            assert needle not in ev_blob, (
                f"raw PII {needle!r} leaked into audit row {ev.id}"
            )

    # raw_complaints holds the raw narrative — exit gate 2's "raw PII
    # only in raw_complaints" requires that the raw narrative remains
    # accessible from the restricted store.
    assert raw.canonical_complaint_id == canonical.complaint_id
    assert "20512345678" in raw.raw_narrative, "RUC missing from raw_complaints"
    assert "47291834" in raw.raw_narrative, "DNI missing from raw_complaints"
    assert raw.storage_policy == "restricted-demo-pii-v1"


# ---------------------------------------------------------------------------
# P11 DQ completion — Annex 1-A integration tests
# ---------------------------------------------------------------------------


_ANNEX_1A_COMPLETE: dict = {
    "institution_id": "SBS-001234",
    "institution_name": "BANCO_DEMO_001",
    "institution_complaint_id": "BCO-A1A-COMPLETE-001",
    "client_submission_id": "a1a-complete",
    "tid_cli": "DNI",
    "nro_cli": "47291834",
    "cod_cli": "CLI-A1A-001",
    "received_at": "2026-05-26",
    "channel_in": "10",
    "channel_operation": "APP_MOVIL",
    "canal_respuesta": "10",
    "ubigeo": "150101",
    "product": "TARJETA_CREDITO",
    "motive": "COBRO_INDEBIDO",
    "submotive": "30",
    "narrative": (
        "Reclamo Annex-1A completo. Descripción suficiente para superar "
        "el umbral de longitud y proveer contexto al supervisor."
    ),
    "amount_claimed": "450.00",
    "moneda": "PEN",
    "status": "atendido",
    "fecha_resolucion": "2026-05-26",
    "resolucion_reclamo": "favor_usuario",
    "bancaseguros": "no",
    "demo_scenario": "p11-dq-complete-valid",
}


@pytest.mark.asyncio
async def test_a1a_fully_valid_payload_is_accepted(client):
    """Exit gate 1: a fully-valid Annex 1-A payload → accepted, no DQ errors."""

    r = await client.post(
        GRANULAR_PATH,
        json=_ANNEX_1A_COMPLETE,
        headers={"Idempotency-Key": _idem_key("a1a-valid")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "accepted", body
    a1a = body["annex_1a_data_quality"]
    assert a1a["error_count"] == 0
    assert a1a["warning_count"] == 0


@pytest.mark.asyncio
async def test_a1a_bancaseguros_without_conditionals_is_rejected(
    client, test_database_url
):
    """Trigger DQ-A1A-024 + 025 by setting bancaseguros=si without
    producto/motivo bancaseguros. Expected: rejected; DQ-A1A-024 in
    audit_events.meta; no second canonical complaint."""

    payload = {
        **_ANNEX_1A_COMPLETE,
        "client_submission_id": "a1a-bancaseguros-missing",
        "bancaseguros": "si",
    }
    r = await client.post(
        GRANULAR_PATH,
        json=payload,
        headers={"Idempotency-Key": _idem_key("a1a-bs")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "rejected", body
    fired = {
        item["rule_id"]
        for item in body["annex_1a_data_quality"]["results"]
    }
    assert "DQ-A1A-024" in fired
    assert "DQ-A1A-025" in fired

    # Audit row check — at least one dq-rule-violated row with rule_id=024.
    from sbs_api.db.models.audit_event import AuditEvent

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            rows = (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.object_id == body["complaint_id"],
                        AuditEvent.action == "dq-rule-violated",
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()
    rule_ids_in_audit = {r.meta.get("rule_id") for r in rows}
    assert "DQ-A1A-024" in rule_ids_in_audit
    assert "DQ-A1A-025" in rule_ids_in_audit


@pytest.mark.asyncio
async def test_a1a_invalid_estado_is_rejected_with_rule_id_in_audit(
    client, test_database_url
):
    """Trigger DQ-A1A-020 with an invalid estado code; expect rejected
    and the rule_id present in an audit row's meta."""

    payload = {
        **_ANNEX_1A_COMPLETE,
        "client_submission_id": "a1a-bad-estado",
        "status": "inventado",
        # Remove fecha_resolucion + resolucion_reclamo so the
        # atendido-conditional rules don't double-fire; we want a
        # focused DQ-A1A-020 trigger.
    }
    payload.pop("fecha_resolucion", None)
    payload.pop("resolucion_reclamo", None)
    r = await client.post(
        GRANULAR_PATH,
        json=payload,
        headers={"Idempotency-Key": _idem_key("a1a-estado")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "rejected", body
    fired = {
        item["rule_id"] for item in body["annex_1a_data_quality"]["results"]
    }
    assert "DQ-A1A-020" in fired

    from sbs_api.db.models.audit_event import AuditEvent

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            rows = (
                await session.execute(
                    select(AuditEvent).where(
                        AuditEvent.object_id == body["complaint_id"],
                        AuditEvent.action == "dq-rule-violated",
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()
    rule_020 = [r for r in rows if r.meta.get("rule_id") == "DQ-A1A-020"]
    assert rule_020, "DQ-A1A-020 audit row missing"
    meta = rule_020[0].meta
    assert meta["field_path"] == "estado"
    assert meta["observed_value"] == "inventado"
    assert meta["severity"] == "error"
