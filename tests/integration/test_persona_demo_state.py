"""Persona demo-state integration (P-RESHAPE-5).

Seeds the cross-persona artefacts (an assignment to Lucía, an FIBrief
awaiting María, a pattern) and asserts:
* Jorge (unit_head) can create an assignment; Lucía (analyst) sees it
  in her inbox and can ack it.
* An analyst CANNOT create an assignment (lacks assignment:create).
* Jorge can override María's FIBrief decision, but only with a
  50-char rationale (shorter → 422).
* María cannot see another supervisor's assignments (inbox is scoped to
  target_user_id).
* Every persona action lands a persona_audit row.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.auth.persona_scopes import (
    ROLE_ANALYST,
    ROLE_SUPERVISOR,
    ROLE_UNIT_HEAD,
)
from sbs_api.db.models.fi_brief import FIBrief
from sbs_api.db.models.persona_audit import PersonaAudit
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

SHARED_VAL = "sandbox-persona-demo-test-001"  # pragma: allowlist secret
NOW = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)


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


def _hdr(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {SHARED_VAL}", "X-SBS-Role": role}


async def _seed_awaiting_brief(test_database_url: str) -> str:
    from sbs_api.db.models.pattern_detection import PatternDetection
    from sbs_api.db.models.peer_risk_analysis import PeerRiskAnalysis

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    pattern_id = str(uuid.uuid4())
    analysis_id = str(uuid.uuid4())
    brief_id = str(uuid.uuid4())
    async with SM() as session:
        session.add(
            PatternDetection(
                pattern_id=pattern_id,
                detected_at=NOW,
                window_start=NOW - timedelta(days=7),
                window_end=NOW,
                institution_code="SBS-001234",
                complaint_category="COBRO_INDEBIDO",
                pattern_type="VOLUME_SPIKE",
                severity_score=0.80,
                severity_band="HIGH",
                contributing_complaint_ids=["A-1"],
                contributing_indecopi_case_ids=None,
                composite_breakdown={},
                triggered_investigation=True,
            )
        )
        await session.flush()
        session.add(
            PeerRiskAnalysis(
                analysis_id=analysis_id,
                pattern_id=pattern_id,
                cohort_id="BANCO:TIER_1",
                peer_count=5,
                percentile=94.0,
                z_score=2.4,
                is_outlier=True,
                forecast={},
                narrative_es="x",
                narrative_en="y",
                model_id="m",
                model_provider="template",
            )
        )
        await session.flush()
        session.add(
            FIBrief(
                brief_id=brief_id,
                peer_risk_analysis_id=analysis_id,
                pattern_id=pattern_id,
                institution_id="SBS-001234",
                motivo_code="COBRO_INDEBIDO",
                status="REJECTED",  # María rejected; Jorge will override
                rejected_by="maria",
                rejected_at=NOW,
                rejection_reason="No amerita por ahora.",
                pattern_summary_es="Resumen.",
                pattern_summary_en="Summary.",
                peer_context_es="Percentil 94.",
                peer_context_en="Percentile 94.",
                suggested_remediation_areas=["FEE_DISCLOSURE"],
                response_deadline=NOW + timedelta(days=20),
                evidence_complaint_count=12,
                evidence_window_start=NOW - timedelta(days=7),
                evidence_window_end=NOW,
                model_id="m",
                model_provider="template",
            )
        )
        await session.commit()
    await engine.dispose()
    return brief_id


@pytest.mark.asyncio
async def test_assignment_create_then_analyst_ack(app_with_secret, test_database_url):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Jorge (unit_head) sends a pattern to Lucía for a deeper look.
        create = await c.post(
            "/v1/internal/persona/assignments",
            json={
                "source_user_id": "jorge",
                "target_user_id": "lucia",
                "target_persona": "analyst",
                "ref_type": "PATTERN",
                "ref_id": "pat-123",
                "note": "Mira este patrón a nivel de reclamos.",
            },
            headers=_hdr(ROLE_UNIT_HEAD),
        )
        assert create.status_code == 201
        assignment_id = create.json()["assignment_id"]

        # Lucía sees it in her inbox.
        inbox = await c.get(
            "/v1/internal/persona/assignments/inbox",
            params={"target_user_id": "lucia"},
            headers=_hdr(ROLE_ANALYST),
        )
        assert inbox.status_code == 200
        assert inbox.json()["total"] == 1

        # Lucía acks.
        ack = await c.post(
            f"/v1/internal/persona/assignments/{assignment_id}/ack",
            json={"actor_user_id": "lucia"},
            headers=_hdr(ROLE_ANALYST),
        )
        assert ack.status_code == 200

        # Inbox now empty.
        inbox2 = await c.get(
            "/v1/internal/persona/assignments/inbox",
            params={"target_user_id": "lucia"},
            headers=_hdr(ROLE_ANALYST),
        )
        assert inbox2.json()["total"] == 0


@pytest.mark.asyncio
async def test_analyst_cannot_create_assignment(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            "/v1/internal/persona/assignments",
            json={
                "source_user_id": "lucia",
                "target_user_id": "maria",
                "target_persona": "supervisor",
                "ref_type": "PATTERN",
                "ref_id": "pat-1",
            },
            headers=_hdr(ROLE_ANALYST),
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_supervisor_inbox_scoped_to_self(app_with_secret, test_database_url):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Create an assignment targeting supervisor "maria".
        await c.post(
            "/v1/internal/persona/assignments",
            json={
                "source_user_id": "jorge",
                "target_user_id": "maria",
                "target_persona": "supervisor",
                "ref_type": "FIBRIEF",
                "ref_id": "fb-1",
            },
            headers=_hdr(ROLE_UNIT_HEAD),
        )
        # A different supervisor "carlos" queries his own inbox — empty.
        other = await c.get(
            "/v1/internal/persona/assignments/inbox",
            params={"target_user_id": "carlos"},
            headers=_hdr(ROLE_SUPERVISOR),
        )
    assert other.status_code == 200
    assert other.json()["total"] == 0


@pytest.mark.asyncio
async def test_unit_head_override_requires_50_char_rationale(
    app_with_secret, test_database_url
):
    brief_id = await _seed_awaiting_brief(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Too-short rationale → 422 (50-char gate).
        short = await c.post(
            f"/v1/internal/persona/fi_briefs/{brief_id}/override",
            json={
                "actor_id": "jorge",
                "new_status": "APPROVED",
                "rationale": "Override.",
            },
            headers=_hdr(ROLE_UNIT_HEAD),
        )
        assert short.status_code == 422

        # >= 50 chars → 201 and the brief flips to APPROVED.
        ok = await c.post(
            f"/v1/internal/persona/fi_briefs/{brief_id}/override",
            json={
                "actor_id": "jorge",
                "new_status": "APPROVED",
                "rationale": (
                    "Reviso la decisión de María: el patrón sostenido amerita "
                    "enviar el brief de retroalimentación a la entidad."
                ),
            },
            headers=_hdr(ROLE_UNIT_HEAD),
        )
        assert ok.status_code == 201
        assert ok.json()["new_status"] == "APPROVED"
        assert ok.json()["prior_status"] == "REJECTED"


@pytest.mark.asyncio
async def test_supervisor_cannot_override(app_with_secret, test_database_url):
    brief_id = await _seed_awaiting_brief(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            f"/v1/internal/persona/fi_briefs/{brief_id}/override",
            json={
                "actor_id": "maria",
                "new_status": "APPROVED",
                "rationale": "x" * 60,
            },
            headers=_hdr(ROLE_SUPERVISOR),
        )
    assert r.status_code == 403  # supervisor lacks fi_brief:override


@pytest.mark.asyncio
async def test_persona_actions_are_audited(app_with_secret, test_database_url):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post(
            "/v1/internal/persona/assignments",
            json={
                "source_user_id": "jorge",
                "target_user_id": "lucia",
                "target_persona": "analyst",
                "ref_type": "PATTERN",
                "ref_id": "pat-audit",
            },
            headers=_hdr(ROLE_UNIT_HEAD),
        )

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            rows = (
                await session.execute(
                    select(PersonaAudit).where(
                        PersonaAudit.action == "assignment-created"
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()
    assert len(rows) >= 1
    assert rows[0].persona == ROLE_UNIT_HEAD
