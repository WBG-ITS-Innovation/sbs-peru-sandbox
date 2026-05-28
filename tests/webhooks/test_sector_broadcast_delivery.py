"""Sector-broadcast delivery (P-RESHAPE-6).

Each recipient gets a signed payload carrying the
``X-Payload-Type: SECTOR_BROADCAST`` header; the receiver verifies the
HMAC with the shared secret. Partial failures mark the broadcast
PARTIALLY_DELIVERED; recipients are tracked independently.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.db.models.pattern_detection import PatternDetection
from sbs_api.db.models.sector_broadcast import (
    SectorBroadcast,
    SectorBroadcastDelivery,
)
from sbs_api.webhook.signing import (
    build_outbound_canonical_request,
    parse_signature_header,
    verify_outbound_signature,
)
from sbs_api.webhooks.sector_broadcast_delivery import (
    PAYLOAD_TYPE,
    PAYLOAD_TYPE_HEADER,
    deliver_sector_broadcast,
)
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

NOW = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
SECRET = b"0" * 32


async def _seed_approved(test_database_url: str, targets: list[str]) -> str:
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    pattern_id = str(uuid.uuid4())
    broadcast_id = str(uuid.uuid4())
    async with SM() as session:
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
                composite_breakdown={},
                triggered_investigation=True,
            )
        )
        await session.flush()
        session.add(
            SectorBroadcast(
                broadcast_id=broadcast_id,
                origin_pattern_id=pattern_id,
                origin_fi_anonymized=True,
                target_fi_codes=targets,
                status="APPROVED",
                threat_summary_es="Amenaza.",
                threat_summary_en="Threat.",
                threat_indicators=["PHISHING_KEYWORD"],
                suggested_controls=["STRENGTHEN_FRAUD_MONITORING"],
                urgency="ELEVATED",
                response_deadline=NOW + timedelta(days=5),
                requires_dual_approval=True,
                model_id="m",
                model_provider="template",
            )
        )
        await session.commit()
    await engine.dispose()
    return broadcast_id


@pytest.mark.asyncio
async def test_delivers_to_all_targets_with_payload_type_header(test_database_url, db_schema):
    targets = [f"SBS-10{i:04d}" for i in range(1, 5)]
    captured = {"payload_type": 0, "verified": 0}

    async def receiver(request: httpx.Request) -> tuple[int, str]:
        if request.headers.get(PAYLOAD_TYPE_HEADER) == PAYLOAD_TYPE:
            captured["payload_type"] += 1
        body = json.loads(request.content.decode())
        canonical = build_outbound_canonical_request(
            method="POST",
            callback_path="/sbs-callback",
            timestamp=request.headers["X-SBS-Timestamp"],
            body=request.content,
            institution_id=body["target_institution_id"],
        )
        presented = parse_signature_header(request.headers["X-SBS-Signature"])
        if verify_outbound_signature(SECRET, canonical, presented):
            captured["verified"] += 1
        return 200, "ok"

    bid = await _seed_approved(test_database_url, targets)
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            outcome = await deliver_sector_broadcast(
                session, broadcast_id=bid, sender=receiver
            )
            await session.commit()
    finally:
        await engine.dispose()

    assert outcome.status == "DELIVERED"
    assert outcome.delivered == 4
    assert captured["payload_type"] == 4
    assert captured["verified"] == 4


@pytest.mark.asyncio
async def test_partial_failure_marks_partially_delivered(test_database_url, db_schema):
    targets = [f"SBS-10{i:04d}" for i in range(1, 5)]

    async def flaky(request: httpx.Request) -> tuple[int, str]:
        body = json.loads(request.content.decode())
        # One target always fails.
        if body["target_institution_id"] == "SBS-100003":
            return 500, "down"
        return 200, "ok"

    bid = await _seed_approved(test_database_url, targets)
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            outcome = await deliver_sector_broadcast(
                session, broadcast_id=bid, sender=flaky
            )
            await session.commit()
            deliveries = (
                await session.execute(
                    select(SectorBroadcastDelivery).where(
                        SectorBroadcastDelivery.broadcast_id == bid
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    assert outcome.status == "PARTIALLY_DELIVERED"
    assert outcome.delivered == 3
    assert outcome.failed == 1
    failed = [d for d in deliveries if d.status == "DELIVERY_FAILED"]
    assert len(failed) == 1
    assert failed[0].target_fi_code == "SBS-100003"
