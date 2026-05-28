"""Sector Broadcast agent — drafting, peer targeting, anonymity (P-RESHAPE-6)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.agents.providers.mock import MockProvider
from sbs_api.agents.sector_broadcast import evaluate_and_draft_broadcast
from sbs_api.db.models.pattern_detection import PatternDetection
from sbs_api.db.models.sector_broadcast import SectorBroadcast
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

NOW = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)


async def _seed_fraud_pattern(session, *, band="HIGH", institution="SBS-001234") -> str:
    pattern_id = str(uuid.uuid4())
    session.add(
        PatternDetection(
            pattern_id=pattern_id,
            detected_at=NOW,
            window_start=NOW - timedelta(hours=72),
            window_end=NOW,
            institution_code=institution,
            complaint_category="FRAUD",
            pattern_type="FRAUD_EMERGENCE",
            severity_score=0.88,
            severity_band=band,
            contributing_complaint_ids=["FR-1", "FR-2"],
            contributing_indecopi_case_ids=["IND-1"],
            composite_breakdown={
                "weights": {"social": 0.30},
                "threat_indicators": ["PHISHING_KEYWORD", "UNAUTHORIZED_FEE_KEYWORD"],
                "social_signal_ids": ["S-1", "S-2"],
            },
            triggered_investigation=True,
        )
    )
    await session.flush()
    return pattern_id


@pytest.mark.asyncio
async def test_drafts_broadcast_targeting_four_peers(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            pattern_id = await _seed_fraud_pattern(session)
            pattern = await session.get(PatternDetection, pattern_id)
            decision = await evaluate_and_draft_broadcast(
                session, pattern=pattern, provider=MockProvider(), now=NOW
            )
            await session.commit()
            broadcast = (
                await session.execute(select(SectorBroadcast))
            ).scalars().one()
    finally:
        await engine.dispose()

    assert decision.drafted is True
    assert broadcast.status == "AWAITING_DUAL_APPROVAL"
    # BANCO:TIER_1 peers (SBS-100001..4), origin excluded.
    assert set(broadcast.target_fi_codes) == {f"SBS-10{i:04d}" for i in range(1, 5)}
    assert "SBS-001234" not in broadcast.target_fi_codes
    assert broadcast.requires_dual_approval is True
    # Suggested controls are fixed enum codes mapped from indicators.
    assert "REVIEW_FEE_DISCLOSURE_FLOWS" in broadcast.suggested_controls
    # Provenance recorded.
    assert broadcast.model_id and broadcast.model_provider


@pytest.mark.asyncio
async def test_threat_summary_is_anonymous(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            pattern_id = await _seed_fraud_pattern(session)
            pattern = await session.get(PatternDetection, pattern_id)
            await evaluate_and_draft_broadcast(
                session, pattern=pattern, provider=MockProvider(), now=NOW
            )
            await session.commit()
            broadcast = (await session.execute(select(SectorBroadcast))).scalars().one()
    finally:
        await engine.dispose()

    # The literal word "peer"/"par" is allowed (the anonymity guarantee
    # itself says "no peer is named"); what must never appear is an
    # institution id or a peer/origin display-name token.
    for field in (broadcast.threat_summary_es, broadcast.threat_summary_en or ""):
        assert "SBS-" not in field  # no origin/peer institution ids
        assert "PEER_" not in field.upper()  # peer display-name prefix
        assert "BANCO_" not in field.upper()  # origin/peer display name


@pytest.mark.asyncio
async def test_does_not_draft_for_non_high(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            pattern_id = await _seed_fraud_pattern(session, band="MEDIUM")
            pattern = await session.get(PatternDetection, pattern_id)
            decision = await evaluate_and_draft_broadcast(
                session, pattern=pattern, provider=MockProvider(), now=NOW
            )
    finally:
        await engine.dispose()
    assert decision.drafted is False
    assert decision.reason == "not_high"


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
            pattern_id = await _seed_fraud_pattern(session)
            pattern = await session.get(PatternDetection, pattern_id)
            with pytest.raises(RuntimeError, match="on-prem"):
                await evaluate_and_draft_broadcast(
                    session, pattern=pattern, provider=cloud, now=NOW
                )
    finally:
        await engine.dispose()
