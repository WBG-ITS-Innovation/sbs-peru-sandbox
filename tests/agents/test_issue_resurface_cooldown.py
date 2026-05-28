"""Issue Resurface 30-day cooldown.

A second brief for the same (institution_id, motivo_code) within 30
days of a *live* brief (APPROVED/SENT/DELIVERED/ACKED) is skipped with
``cooldown_active``. A rejected brief does NOT block a fresh one.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
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
MOTIVO = "COBRO_INDEBIDO"
INST = "SBS-001234"


async def _seed(session) -> tuple[PatternDetection, str]:
    pattern_id = str(uuid.uuid4())
    session.add(
        PatternDetection(
            pattern_id=pattern_id,
            detected_at=NOW,
            window_start=NOW - timedelta(days=7),
            window_end=NOW,
            institution_code=INST,
            complaint_category=MOTIVO,
            pattern_type="VOLUME_SPIKE",
            severity_score=0.80,
            severity_band="HIGH",
            contributing_complaint_ids=["IR-1", "IR-2"],
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
    await session.flush()
    from sqlalchemy import select

    pattern = (
        await session.execute(
            select(PatternDetection).where(PatternDetection.pattern_id == pattern_id)
        )
    ).scalar_one()
    return pattern, analysis_id


def _peer(analysis_id: str) -> PeerRiskResult:
    return PeerRiskResult(
        analysis_id=analysis_id,
        cohort_id="BANCO:TIER_1",
        peer_count=5,
        percentile=94.0,
        z_score=2.4,
        is_outlier=True,
        sustained_days_above_p90=9,
        forecast={},
        narrative_es="x",
        narrative_en="y",
        model_id="m",
        model_provider="template",
    )


@pytest.mark.asyncio
async def test_second_brief_within_30d_skipped(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            pattern, analysis_id = await _seed(session)
            first = await evaluate_and_draft(
                session, pattern=pattern, peer_risk=_peer(analysis_id),
                provider=MockProvider(), now=NOW,
            )
            # Promote the first brief to a "live" (cooldown-counting) status.
            brief = (await session.get(FIBrief, first.brief_id))
            brief.status = "SENT"
            await session.flush()

            second = await evaluate_and_draft(
                session, pattern=pattern, peer_risk=_peer(analysis_id),
                provider=MockProvider(), now=NOW + timedelta(days=5),
            )
            await session.commit()
    finally:
        await engine.dispose()

    assert first.drafted is True
    assert second.drafted is False
    assert second.reason == "cooldown_active"


@pytest.mark.asyncio
async def test_rejected_brief_does_not_block(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            pattern, analysis_id = await _seed(session)
            first = await evaluate_and_draft(
                session, pattern=pattern, peer_risk=_peer(analysis_id),
                provider=MockProvider(), now=NOW,
            )
            brief = await session.get(FIBrief, first.brief_id)
            brief.status = "REJECTED"  # not a cooldown-counting status
            await session.flush()

            second = await evaluate_and_draft(
                session, pattern=pattern, peer_risk=_peer(analysis_id),
                provider=MockProvider(), now=NOW + timedelta(days=2),
            )
            await session.commit()
    finally:
        await engine.dispose()

    assert first.drafted is True
    assert second.drafted is True  # rejected brief did not block
