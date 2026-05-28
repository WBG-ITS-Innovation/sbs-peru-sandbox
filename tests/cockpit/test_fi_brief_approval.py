"""FIBrief approval gate + ack endpoint via the FastAPI app.

Mirrors the existing approvals-endpoint test harness. Verifies:
* 20-char rationale gate (server-enforced via Pydantic)
* head-only role gate
* approve transitions the brief out of AWAITING_APPROVAL and attempts
  delivery (delivery target is unreachable in tests → DELIVERY_FAILED,
  which still proves the gate + transition)
* ack endpoint persists payload + flips status to ACKED
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.db.models.fi_brief import FIBrief
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

SHARED_VAL = "sandbox-fibrief-test-1122334455"  # pragma: allowlist secret
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


async def _seed_awaiting_brief(test_database_url: str, institution_id="SBS-001234") -> str:
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
                institution_code=institution_id,
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
        # Flush parents before the FIBrief so the FK targets exist.
        await session.flush()
        session.add(
            FIBrief(
                brief_id=brief_id,
                peer_risk_analysis_id=analysis_id,
                pattern_id=pattern_id,
                institution_id=institution_id,
                motivo_code="COBRO_INDEBIDO",
                status="AWAITING_APPROVAL",
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


def _head() -> dict[str, str]:
    return {"Authorization": f"Bearer {SHARED_VAL}", "X-SBS-Role": "sbs:conduct:head"}


@pytest.mark.asyncio
async def test_approve_requires_20char_rationale(app_with_secret, test_database_url):
    brief_id = await _seed_awaiting_brief(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            f"/v1/internal/fi_briefs/{brief_id}/approve",
            json={"actor_id": "head-1", "rationale": "too short"},
            headers=_head(),
        )
    assert r.status_code == 422  # Pydantic min_length=20


@pytest.mark.asyncio
async def test_approve_with_rationale_transitions_and_delivers(
    app_with_secret, test_database_url
):
    brief_id = await _seed_awaiting_brief(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            f"/v1/internal/fi_briefs/{brief_id}/approve",
            json={
                "actor_id": "head-1",
                "rationale": "Confirmed sustained outlier, send pre-escalation brief.",
            },
            headers=_head(),
        )
    assert r.status_code == 201
    body = r.json()
    # Delivery target (compose listener) is unreachable in tests, so the
    # status walks to DELIVERY_FAILED — the gate + transition are proven.
    assert body["status"] in {"DELIVERED", "DELIVERY_FAILED", "SENT"}

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            brief = await session.get(FIBrief, brief_id)
    finally:
        await engine.dispose()
    assert brief.approved_by == "head-1"
    assert brief.approval_rationale
    assert brief.status != "AWAITING_APPROVAL"


@pytest.mark.asyncio
async def test_non_head_role_forbidden(app_with_secret, test_database_url):
    brief_id = await _seed_awaiting_brief(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            f"/v1/internal/fi_briefs/{brief_id}/approve",
            json={"actor_id": "x", "rationale": "a" * 25},
            headers={
                "Authorization": f"Bearer {SHARED_VAL}",
                "X-SBS-Role": "sbs:conduct:analyst",
            },
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_ack_endpoint_persists_payload(app_with_secret, test_database_url):
    brief_id = await _seed_awaiting_brief(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            f"/v1/internal/fi_brief/{brief_id}/ack",
            json={"response_codes": ["REMEDIATION_PLANNED"], "note": "Working on it."},
            headers={"Authorization": f"Bearer {SHARED_VAL}"},
        )
    assert r.status_code == 202

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            brief = await session.get(FIBrief, brief_id)
    finally:
        await engine.dispose()
    assert brief.status == "ACKED"
    assert brief.ack_received_at is not None
    assert brief.ack_payload["response_codes"] == ["REMEDIATION_PLANNED"]
