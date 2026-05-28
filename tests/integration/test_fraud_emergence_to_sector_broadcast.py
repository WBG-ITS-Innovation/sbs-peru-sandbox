"""Full fraud chain (P-RESHAPE-6): social + complaints + INDECOPI fuse
into a FRAUD_EMERGENCE detection → Investigation → PRR → Sector
Broadcast (AWAITING_DUAL_APPROVAL) → dual approval → signed delivery to
cohort peers.

The chain test prints a LOG-only narrative summary of what happened
end-to-end (no business data) — the demo's emotional payoff.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.aggregation.tick import run_aggregation_tick
from sbs_api.agents.orchestrator import run_investigation_from_pattern
from sbs_api.agents.providers import reset_provider_cache
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.indecopi_case import IndecopiCase
from sbs_api.db.models.pattern_detection import PatternDetection
from sbs_api.db.models.sector_broadcast import (
    SectorBroadcast,
    SectorBroadcastDelivery,
)
from sbs_api.ingestion.social.fixture_adapter import FixtureSocialAdapter
from sbs_api.ingestion.social.runner import run_social_ingestion
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
ORIGIN = "SBS-001234"
SECRET = b"0" * 32


def _complaint(cid: str, motivo: str, received_at: datetime) -> ComplaintRecord:
    return ComplaintRecord(
        complaint_id=cid,
        institution_id=ORIGIN,
        received_date=received_at.date(),
        complainant_doc_type="DNI",
        product_category="TARJETA_CREDITO",
        channel="APP_MOVIL",
        motivo_code=motivo,
        severity="HIGH",
        description_text="Reclamo de fraude para cadena completa.",
        description_language="es",
        complainant_age_range="35_44",
        complainant_district="150100",
        submission_method="APP_MOVIL",
        resolution_status="pendiente",
        source="api_realtime",
        received_at=received_at,
    )


async def _seed_fraud_corpus(session) -> None:
    # 4 fraud-category complaints in last 24h.
    for i in range(4):
        session.add(
            _complaint(f"FR-C-{i:06d}", "OPERACION_NO_RECONOCIDA", NOW - timedelta(hours=2 + i))
        )
    # 3 fraud INDECOPI cases in last 7d.
    for i in range(3):
        session.add(
            IndecopiCase(
                case_id=f"FR-IND-{i}",
                institution_id=ORIGIN,
                complaint_category="OPERACION_NO_RECONOCIDA",
                opened_at=NOW - timedelta(days=1 + i),
            )
        )
    # Ingest the 14 seeded social signals into the live table.
    await run_social_ingestion(
        session, adapters=[FixtureSocialAdapter(session)], now=NOW
    )
    await session.flush()


@pytest.mark.asyncio
async def test_full_fraud_chain(test_database_url, db_schema, monkeypatch, caplog):
    monkeypatch.setenv("SBS_API_MODEL_PROVIDER", "mock")
    reset_provider_cache()

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            await _seed_fraud_corpus(session)
            tick = await run_aggregation_tick(session, now=NOW)
            await session.commit()

            fraud_rows = (
                await session.execute(
                    select(PatternDetection).where(
                        PatternDetection.pattern_type == "FRAUD_EMERGENCE"
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    # FRAUD_EMERGENCE detected, HIGH, on the origin FI.
    assert len(fraud_rows) == 1
    fraud_pattern = fraud_rows[0]
    assert fraud_pattern.severity_band == "HIGH"
    assert fraud_pattern.institution_code == ORIGIN
    assert fraud_pattern.pattern_id in tick.high_pattern_ids
    # The fraud composite used the locked fraud-weight set (social channel).
    assert "social" in fraud_pattern.composite_breakdown["weights"]

    # Drive Investigation → PRR → Sector Broadcast off the fraud pattern.
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            dossier = await run_investigation_from_pattern(
                session, pattern_id=fraud_pattern.pattern_id
            )
            await session.commit()

            broadcast = (
                await session.execute(select(SectorBroadcast))
            ).scalars().first()
    finally:
        await engine.dispose()

    # Sector broadcast drafted, awaiting dual approval, targeting the 4
    # BANCO:TIER_1 peers (origin excluded).
    assert dossier["sector_broadcast"]["drafted"] is True
    assert broadcast is not None
    assert broadcast.status == "AWAITING_DUAL_APPROVAL"
    assert set(broadcast.target_fi_codes) == {
        f"SBS-10{i:04d}" for i in range(1, 5)
    }
    assert ORIGIN not in broadcast.target_fi_codes
    assert broadcast.threat_indicators  # carried from the fraud pattern

    # --- Dual approval + delivery with an in-process verifying receiver ---
    broadcast_id = broadcast.broadcast_id
    captured: dict[str, int] = {"verified": 0, "payload_type_ok": 0}

    async def verifying_receiver(request: httpx.Request) -> tuple[int, str]:
        if request.headers.get(PAYLOAD_TYPE_HEADER) == PAYLOAD_TYPE:
            captured["payload_type_ok"] += 1
        target = request.headers["X-SBS-Signature"]
        presented = parse_signature_header(target)
        # Recover institution from the JSON body for the canonical check.
        import json as _json

        body = _json.loads(request.content.decode())
        canonical = build_outbound_canonical_request(
            method="POST",
            callback_path="/sbs-callback",
            timestamp=request.headers["X-SBS-Timestamp"],
            body=request.content,
            institution_id=body["target_institution_id"],
        )
        if verify_outbound_signature(SECRET, canonical, presented):
            captured["verified"] += 1
        return 200, "ok"

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            b = await session.get(SectorBroadcast, broadcast_id)
            b.status = "APPROVED"
            await session.flush()
            outcome = await deliver_sector_broadcast(
                session, broadcast_id=broadcast_id, sender=verifying_receiver
            )
            await session.commit()

            deliveries = (
                await session.execute(
                    select(SectorBroadcastDelivery).where(
                        SectorBroadcastDelivery.broadcast_id == broadcast_id
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    assert outcome.status == "DELIVERED"
    assert outcome.delivered == 4
    assert captured["verified"] == 4
    assert captured["payload_type_ok"] == 4
    assert all(d.status == "DELIVERED" for d in deliveries)

    # LOG-only narrative payoff (no business data).
    logging.getLogger(__name__).info(
        "FRAUD CHAIN: 14 social signals + %d fraud complaints + %d INDECOPI "
        "cases fused into 1 HIGH FRAUD_EMERGENCE pattern; Investigation + PRR "
        "ran; sector broadcast warned %d cohort peers after dual approval.",
        4,
        3,
        outcome.delivered,
    )
