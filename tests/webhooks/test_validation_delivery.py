# SPDX-License-Identifier: Apache-2.0
"""DIValeVale validation webhook delivery (P-RESHAPE-8). DB-backed.

Both payload types sign with the existing HMAC chain and carry the
right X-Payload-Type. Payloads contain codes + ids only — no narrative.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.webhook.signing import (
    build_outbound_canonical_request,
    parse_signature_header,
    verify_outbound_signature,
)
from sbs_api.webhooks.validation_delivery import (
    PAYLOAD_BATCH_REJECTION,
    PAYLOAD_ENRICHMENT_REQUEST,
    PAYLOAD_TYPE_HEADER,
    build_batch_rejection_payload,
    build_enrichment_request_payload,
    deliver_batch_rejection,
    deliver_enrichment_request,
)
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

SECRET = b"0" * 32
NOW = datetime(2026, 5, 28, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_batch_rejection_signed_with_payload_type(test_database_url, db_schema):
    captured: dict = {}

    async def receiver(req: httpx.Request) -> tuple[int, str]:
        captured["type"] = req.headers.get(PAYLOAD_TYPE_HEADER)
        canonical = build_outbound_canonical_request(
            method="POST", callback_path="/sbs-callback",
            timestamp=req.headers["X-SBS-Timestamp"], body=req.content,
            institution_id="SBS-001234",
        )
        presented = parse_signature_header(req.headers["X-SBS-Signature"])
        captured["valid"] = verify_outbound_signature(SECRET, canonical, presented)
        captured["body"] = req.content.decode()
        return 200, "ok"

    payload = build_batch_rejection_payload(
        batch_id="DEMO_BATCH_001", row_count=10,
        per_row_codes=[{"row_ref": "BATCH-009", "verdict": "INVALID", "codes": ["MOTIVO_CODE_INVALID"]}],
        resubmit_url="https://x/resubmit",
    )
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            outcome = await deliver_batch_rejection(
                session, sbs_institution_id="SBS-001234", payload=payload, sender=receiver
            )
    finally:
        await engine.dispose()
    assert outcome.status == "DELIVERED"
    assert captured["type"] == PAYLOAD_BATCH_REJECTION
    assert captured["valid"] is True
    # Codes only — no narrative text in the payload.
    body = json.loads(captured["body"])
    assert body["per_row_failure_codes"][0]["codes"] == ["MOTIVO_CODE_INVALID"]
    assert "narrative" not in captured["body"].lower()


@pytest.mark.asyncio
async def test_enrichment_request_signed_with_payload_type(test_database_url, db_schema):
    captured: dict = {}

    async def receiver(req: httpx.Request) -> tuple[int, str]:
        captured["type"] = req.headers.get(PAYLOAD_TYPE_HEADER)
        captured["body"] = req.content.decode()
        return 200, "ok"

    payload = build_enrichment_request_payload(
        complaint_id="BCO-2026-000004",
        missing_fields=["NARRATIVE_TOO_SHORT", "AMOUNT_CLAIMED_MISSING"],
        deadline=NOW + timedelta(days=5),
        resubmit_url="https://x/resubmit",
    )
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            outcome = await deliver_enrichment_request(
                session, sbs_institution_id="SBS-001234", payload=payload, sender=receiver
            )
    finally:
        await engine.dispose()
    assert outcome.status == "DELIVERED"
    assert captured["type"] == PAYLOAD_ENRICHMENT_REQUEST
    body = json.loads(captured["body"])
    assert body["complaint_id"] == "BCO-2026-000004"
    assert "missing_fields" in body
