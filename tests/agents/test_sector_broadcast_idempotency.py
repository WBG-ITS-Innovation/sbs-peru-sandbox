"""Sector broadcast idempotency (P-RESHAPE-6).

Re-drafting for the same origin pattern does not create a second
broadcast. Re-delivering does not re-send to an already-DELIVERED
recipient.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.agents.providers.mock import MockProvider
from sbs_api.agents.sector_broadcast import evaluate_and_draft_broadcast
from sbs_api.db.models.pattern_detection import PatternDetection
from sbs_api.db.models.sector_broadcast import (
    SectorBroadcast,
    SectorBroadcastDelivery,
)
from sbs_api.webhooks.sector_broadcast_delivery import deliver_sector_broadcast
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

NOW = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)


async def _seed_pattern(session) -> str:
    pattern_id = str(uuid.uuid4())
    session.add(
        PatternDetection(
            pattern_id=pattern_id,
            detected_at=NOW,
            window_start=NOW - timedelta(hours=72),
            window_end=NOW,
            institution_code="SBS-001234",
            complaint_category="FRAUD",
            pattern_type="FRAUD_EMERGENCE",
            severity_score=0.88,
            severity_band="HIGH",
            contributing_complaint_ids=["FR-1"],
            contributing_indecopi_case_ids=None,
            composite_breakdown={"threat_indicators": ["PHISHING_KEYWORD"]},
            triggered_investigation=True,
        )
    )
    await session.flush()
    return pattern_id


@pytest.mark.asyncio
async def test_redraft_is_idempotent(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            pattern_id = await _seed_pattern(session)
            pattern = await session.get(PatternDetection, pattern_id)
            first = await evaluate_and_draft_broadcast(
                session, pattern=pattern, provider=MockProvider(), now=NOW
            )
            second = await evaluate_and_draft_broadcast(
                session, pattern=pattern, provider=MockProvider(), now=NOW
            )
            await session.commit()
            count = (
                await session.execute(select(func.count()).select_from(SectorBroadcast))
            ).scalar_one()
    finally:
        await engine.dispose()
    assert first.drafted is True
    assert second.drafted is False
    assert second.reason == "already_drafted"
    assert count == 1


@pytest.mark.asyncio
async def test_redeliver_skips_already_delivered(test_database_url, db_schema):
    sends: list[str] = []

    async def ok_sender(request: httpx.Request) -> tuple[int, str]:
        sends.append(request.url.path)
        return 200, "ok"

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            pattern_id = await _seed_pattern(session)
            pattern = await session.get(PatternDetection, pattern_id)
            decision = await evaluate_and_draft_broadcast(
                session, pattern=pattern, provider=MockProvider(), now=NOW
            )
            broadcast = await session.get(SectorBroadcast, decision.broadcast_id)
            broadcast.status = "APPROVED"
            await session.flush()

            first = await deliver_sector_broadcast(
                session, broadcast_id=decision.broadcast_id, sender=ok_sender
            )
            sends_after_first = len(sends)

            # Re-deliver — every recipient already DELIVERED → no new sends.
            second = await deliver_sector_broadcast(
                session, broadcast_id=decision.broadcast_id, sender=ok_sender
            )
            await session.commit()

            deliveries = (
                await session.execute(
                    select(SectorBroadcastDelivery).where(
                        SectorBroadcastDelivery.broadcast_id == decision.broadcast_id
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    assert first.delivered == 4
    assert sends_after_first == 4
    assert second.skipped_already_delivered == 4
    assert len(sends) == 4  # no extra sends on re-delivery
    assert len(deliveries) == 4
