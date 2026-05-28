"""Issue Resurface agent — trigger conditions + draft shape.

Exercises ``evaluate_and_draft`` against a seeded HIGH pattern +
PeerRiskResult. DB-gated (FIBrief has FKs to pattern_detections +
peer_risk_analyses).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.agents.issue_resurface import evaluate_and_draft
from sbs_api.agents.peer_risk_radar import PeerRiskResult
from sbs_api.agents.providers.mock import MockProvider
from sbs_api.db.models.fi_brief import FIBrief
from sbs_api.db.models.pattern_detection import PatternDetection
from sbs_api.db.models.peer_risk_analysis import PeerRiskAnalysis
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

NOW = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)


async def _seed_pattern_and_analysis(
    session, *, institution_id="SBS-001234", motivo="COBRO_INDEBIDO"
) -> tuple[PatternDetection, str]:
    pattern_id = str(uuid.uuid4())
    session.add(
        PatternDetection(
            pattern_id=pattern_id,
            detected_at=NOW,
            window_start=NOW - timedelta(days=7),
            window_end=NOW,
            institution_code=institution_id,
            complaint_category=motivo,
            pattern_type="VOLUME_SPIKE",
            severity_score=0.80,
            severity_band="HIGH",
            contributing_complaint_ids=[f"IR-{i:06d}" for i in range(12)],
            contributing_indecopi_case_ids=None,
            composite_breakdown={"weights": {}},
            triggered_investigation=True,
            investigation_run_id=None,
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
            forecast={"trend_direction": "RISING"},
            narrative_es="Narrativa de prueba.",
            narrative_en="Test narrative.",
            model_id="prr-template-fallback-v1",
            model_provider="template",
        )
    )
    await session.flush()
    pattern = (
        await session.execute(
            select(PatternDetection).where(PatternDetection.pattern_id == pattern_id)
        )
    ).scalar_one()
    return pattern, analysis_id


def _peer_result(analysis_id: str, *, is_outlier=True, percentile=94.0, sustained=9) -> PeerRiskResult:
    return PeerRiskResult(
        analysis_id=analysis_id,
        cohort_id="BANCO:TIER_1",
        peer_count=5,
        percentile=percentile,
        z_score=2.4,
        is_outlier=is_outlier,
        sustained_days_above_p90=sustained,
        forecast={"trend_direction": "RISING"},
        narrative_es="x",
        narrative_en="y",
        model_id="prr-template-fallback-v1",
        model_provider="template",
    )


@pytest.mark.asyncio
async def test_all_conditions_met_drafts_awaiting_approval(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            pattern, analysis_id = await _seed_pattern_and_analysis(session)
            decision = await evaluate_and_draft(
                session,
                pattern=pattern,
                peer_risk=_peer_result(analysis_id),
                provider=MockProvider(),
                now=NOW,
            )
            await session.commit()

            brief = (
                await session.execute(
                    select(FIBrief).where(FIBrief.brief_id == decision.brief_id)
                )
            ).scalar_one()
    finally:
        await engine.dispose()

    assert decision.drafted is True
    assert decision.reason == "drafted"
    assert brief.status == "AWAITING_APPROVAL"
    # Remediation areas are fixed enum codes mapped from the motivo.
    assert "FEE_DISCLOSURE" in brief.suggested_remediation_areas
    # Provenance mandatory.
    assert brief.model_id
    assert brief.model_provider
    # Deadline is 15 business days out.
    assert brief.response_deadline > NOW


@pytest.mark.asyncio
async def test_not_outlier_skips(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            pattern, analysis_id = await _seed_pattern_and_analysis(session)
            decision = await evaluate_and_draft(
                session,
                pattern=pattern,
                peer_risk=_peer_result(analysis_id, is_outlier=False),
                provider=MockProvider(),
                now=NOW,
            )
    finally:
        await engine.dispose()
    assert decision.drafted is False
    assert decision.reason == "not_outlier"


@pytest.mark.asyncio
async def test_not_sustained_skips(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            pattern, analysis_id = await _seed_pattern_and_analysis(session)
            decision = await evaluate_and_draft(
                session,
                pattern=pattern,
                peer_risk=_peer_result(analysis_id, sustained=3),
                provider=MockProvider(),
                now=NOW,
            )
    finally:
        await engine.dispose()
    assert decision.drafted is False
    assert decision.reason == "not_sustained"


@pytest.mark.asyncio
async def test_cloud_provider_rejected(test_database_url, db_schema):
    import os

    os.environ["SBS_API_CLOUD_LEGAL_APPROVED"] = "true"
    try:
        from sbs_api.agents.providers.cloud import CloudProvider

        cloud = CloudProvider()
    except NotImplementedError:
        pytest.skip("CloudProvider gate raises upstream")
        return
    finally:
        os.environ.pop("SBS_API_CLOUD_LEGAL_APPROVED", None)

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            pattern, analysis_id = await _seed_pattern_and_analysis(session)
            with pytest.raises(RuntimeError, match="on-prem"):
                await evaluate_and_draft(
                    session,
                    pattern=pattern,
                    peer_risk=_peer_result(analysis_id),
                    provider=cloud,
                    now=NOW,
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_peer_context_is_peer_anonymous(test_database_url, db_schema):
    """The peer-context narrative must never name a peer institution id."""
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            pattern, analysis_id = await _seed_pattern_and_analysis(session)
            decision = await evaluate_and_draft(
                session,
                pattern=pattern,
                peer_risk=_peer_result(analysis_id),
                provider=MockProvider(),
                now=NOW,
            )
            await session.commit()
            brief = (
                await session.execute(
                    select(FIBrief).where(FIBrief.brief_id == decision.brief_id)
                )
            ).scalar_one()
    finally:
        await engine.dispose()

    # No peer institution_id token (and no peer display-name) anywhere
    # in the peer-context narrative. The literal word "peer"/"par" is
    # allowed — the anonymity guarantee itself says "no peer is named".
    for field in (brief.peer_context_es, brief.peer_context_en or ""):
        assert "SBS-10" not in field  # peer institution ids
        assert "SBS-20" not in field
        assert "PEER_" not in field.upper()  # peer display-name prefix
