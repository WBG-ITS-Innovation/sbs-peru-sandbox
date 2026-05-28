"""FI brief delivery — retry behaviour + valid HMAC signature.

The HTTP send is injected (``sender``) so the retry path is testable
without a live receiver. The signature is verified with the SAME
helper an FI would use, proving the existing signed-webhook chain is
reused end-to-end.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.db.models.fi_brief import FIBrief
from sbs_api.db.models.fi_brief_audit import FIBriefAudit
from sbs_api.webhook.signing import (
    build_outbound_canonical_request,
    parse_signature_header,
    verify_outbound_signature,
)
from sbs_api.webhooks.fi_brief_delivery import deliver_fi_brief
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

NOW = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
SECRET = b"0" * 32  # matches conftest seed


async def _seed_approved_brief(session, *, institution_id="SBS-001234") -> str:
    # FIBrief FKs require a pattern + analysis row.
    from sbs_api.db.models.pattern_detection import PatternDetection
    from sbs_api.db.models.peer_risk_analysis import PeerRiskAnalysis

    pattern_id = str(uuid.uuid4())
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
            contributing_complaint_ids=["D-1", "D-2"],
            contributing_indecopi_case_ids=None,
            composite_breakdown={},
            triggered_investigation=True,
        )
    )
    analysis_id = str(uuid.uuid4())
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
    brief_id = str(uuid.uuid4())
    session.add(
        FIBrief(
            brief_id=brief_id,
            peer_risk_analysis_id=analysis_id,
            pattern_id=pattern_id,
            institution_id=institution_id,
            motivo_code="COBRO_INDEBIDO",
            status="APPROVED",
            pattern_summary_es="Resumen.",
            pattern_summary_en="Summary.",
            peer_context_es="Percentil 94.",
            peer_context_en="Percentile 94.",
            suggested_remediation_areas=["FEE_DISCLOSURE"],
            response_deadline=NOW + timedelta(days=20),
            evidence_complaint_count=12,
            evidence_window_start=NOW - timedelta(days=7),
            evidence_window_end=NOW,
            approved_by="head-1",
            approved_at=NOW,
            approval_rationale="Approved for delivery in test scenario.",
            model_id="m",
            model_provider="template",
        )
    )
    await session.flush()
    return brief_id


@pytest.mark.asyncio
async def test_delivery_retries_twice_then_succeeds(test_database_url, db_schema):
    calls: list[int] = []

    async def flaky_sender(request: httpx.Request) -> tuple[int, str]:
        calls.append(1)
        if len(calls) < 3:
            return 503, "try later"
        return 200, "ok"

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            brief_id = await _seed_approved_brief(session)
            outcome = await deliver_fi_brief(
                session, brief_id=brief_id, sender=flaky_sender
            )
            await session.commit()

            brief = await session.get(FIBrief, brief_id)
            attempts_logged = (
                await session.execute(
                    select(FIBriefAudit).where(
                        FIBriefAudit.brief_id == brief_id,
                        FIBriefAudit.event_type == "delivery_attempt",
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    assert outcome.status == "DELIVERED"
    assert outcome.attempts == 3
    assert brief.status == "DELIVERED"
    assert brief.delivery_attempts == 3
    assert brief.delivered_at is not None
    assert len(attempts_logged) == 3


@pytest.mark.asyncio
async def test_delivery_exhaustion_marks_failed(test_database_url, db_schema):
    async def always_fail(request: httpx.Request) -> tuple[int, str]:
        return 500, "down"

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            brief_id = await _seed_approved_brief(session)
            outcome = await deliver_fi_brief(
                session, brief_id=brief_id, sender=always_fail
            )
            await session.commit()
    finally:
        await engine.dispose()

    assert outcome.status == "DELIVERY_FAILED"
    assert outcome.attempts == 3


@pytest.mark.asyncio
async def test_delivery_signature_is_valid(test_database_url, db_schema):
    """The receiver can verify the signature with the shared secret —
    proving the existing HMAC chain is correctly reused."""
    captured: dict[str, httpx.Request] = {}

    async def capturing_sender(request: httpx.Request) -> tuple[int, str]:
        captured["req"] = request
        return 200, "ok"

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            brief_id = await _seed_approved_brief(session)
            await deliver_fi_brief(
                session, brief_id=brief_id, sender=capturing_sender
            )
            await session.commit()
    finally:
        await engine.dispose()

    req = captured["req"]
    presented = parse_signature_header(req.headers["X-SBS-Signature"])
    canonical = build_outbound_canonical_request(
        method="POST",
        callback_path="/sbs-callback",
        timestamp=req.headers["X-SBS-Timestamp"],
        body=req.content,
        institution_id="SBS-001234",
    )
    assert verify_outbound_signature(SECRET, canonical, presented)
