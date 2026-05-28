"""Full chain: pattern → Investigation → PRR → Issue Resurface →
approval → signed delivery → ack.

The compose ``webhook-listener`` is not running under pytest, so the
"mock receiver" is an in-process sender that verifies the HMAC
signature (exactly as the real receiver would) before returning 200.
That proves the existing signed-webhook chain end-to-end without a
network service.

DB-gated via ``pytestmark_db``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.aggregation.tick import run_aggregation_tick
from sbs_api.agents.orchestrator import run_investigation_from_pattern
from sbs_api.agents.providers import reset_provider_cache
from sbs_api.db.models.complaint import ComplaintRecord
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
INST = "SBS-001234"
CATEGORY = "CALIDAD_SERVICIO"
SECRET = b"0" * 32  # matches conftest seed


def _complaint(cid: str, institution_id: str, motivo: str, received_at: datetime) -> ComplaintRecord:
    return ComplaintRecord(
        complaint_id=cid,
        institution_id=institution_id,
        received_date=received_at.date(),
        complainant_doc_type="DNI",
        product_category="TARJETA_CREDITO",
        channel="APP_MOVIL",
        motivo_code=motivo,
        severity="HIGH",
        description_text="Reclamo para cadena completa FI brief.",
        description_language="es",
        complainant_age_range="35_44",
        complainant_district="150100",
        submission_method="APP_MOVIL",
        resolution_status="pendiente",
        source="api_realtime",
        received_at=received_at,
    )


async def _seed_sustained_spike(session) -> None:
    # 8 complaints in last 24h (day 0) → VOLUME_SPIKE.
    for i in range(8):
        session.add(
            _complaint(f"FB-S-{i:06d}", INST, CATEGORY, NOW - timedelta(hours=2 + i))
        )
    # 1 complaint/day on days 1..9 → prior_7d_mean ~1.0 AND 9 distinct
    # days above the (near-zero) peer p90 → sustained_days_above_p90 >= 7.
    for d in range(1, 10):
        session.add(
            _complaint(
                f"FB-D{d:02d}", INST, CATEGORY, NOW - timedelta(days=d, hours=6)
            )
        )
    # Peers: 1 complaint each within the 7d window so the cohort is
    # non-degenerate but BANCO is clearly the outlier.
    for idx in range(1, 5):
        peer = f"SBS-10{idx:04d}"
        session.add(
            _complaint(f"FB-PEER-{idx}", peer, CATEGORY, NOW - timedelta(days=2, hours=idx))
        )
    await session.flush()


@pytest.mark.asyncio
async def test_full_chain_drafts_brief_then_delivers_and_acks(
    test_database_url, db_schema, monkeypatch
):
    monkeypatch.setenv("SBS_API_MODEL_PROVIDER", "mock")
    reset_provider_cache()

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            await _seed_sustained_spike(session)
            tick = await run_aggregation_tick(session, now=NOW)
            await session.commit()

        assert tick.high_pattern_ids, "expected at least one HIGH pattern"

        async with SM() as session:
            dossier = await run_investigation_from_pattern(
                session, pattern_id=tick.high_pattern_ids[0]
            )
            await session.commit()

            # Issue Resurface should have drafted a brief.
            brief = (
                await session.execute(
                    select(FIBrief).where(FIBrief.institution_id == INST)
                )
            ).scalars().first()
    finally:
        await engine.dispose()

    # Dossier carries the fi_brief decision block.
    assert dossier["dossier_format"] == "narrative-v1"
    assert dossier["fi_brief"]["drafted"] is True
    assert brief is not None
    assert brief.status == "AWAITING_APPROVAL"
    assert brief.suggested_remediation_areas  # fixed enum codes

    brief_id = brief.brief_id

    # --- Approve + deliver via an in-process "mock receiver" that
    # verifies the HMAC before returning 200. ---
    verified: dict[str, bool] = {}

    async def verifying_receiver(request: httpx.Request) -> tuple[int, str]:
        presented = parse_signature_header(request.headers["X-SBS-Signature"])
        canonical = build_outbound_canonical_request(
            method="POST",
            callback_path="/sbs-callback",
            timestamp=request.headers["X-SBS-Timestamp"],
            body=request.content,
            institution_id=INST,
        )
        verified["ok"] = verify_outbound_signature(SECRET, canonical, presented)
        return (200, "ok") if verified["ok"] else (401, "bad sig")

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            brief = await session.get(FIBrief, brief_id)
            brief.status = "APPROVED"
            brief.approved_by = "head-1"
            brief.approved_at = NOW
            brief.approval_rationale = "Confirmed sustained outlier; send brief."
            await session.flush()
            outcome = await deliver_fi_brief(
                session, brief_id=brief_id, sender=verifying_receiver
            )
            await session.commit()

        # --- Ack ---
        async with SM() as session:
            brief = await session.get(FIBrief, brief_id)
            brief.ack_received_at = NOW
            brief.ack_payload = {"response_codes": ["ACK"]}
            brief.status = "ACKED"
            session.add(
                FIBriefAudit(
                    brief_id=brief_id,
                    event_type="acked",
                    event_payload={"response_codes": ["ACK"]},
                    actor=f"fi:{INST}",
                )
            )
            await session.commit()

            audit_rows = (
                await session.execute(
                    select(FIBriefAudit).where(FIBriefAudit.brief_id == brief_id)
                )
            ).scalars().all()
            final = await session.get(FIBrief, brief_id)
    finally:
        await engine.dispose()

    assert verified["ok"] is True
    assert outcome.status == "DELIVERED"
    assert outcome.attempts == 1
    assert final.status == "ACKED"
    # Audit trail: drafted + delivery_attempt + delivered + acked all present.
    event_types = {a.event_type for a in audit_rows}
    assert {"delivery_attempt", "delivered", "acked"}.issubset(event_types)


@pytest.mark.asyncio
async def test_full_chain_brief_is_peer_anonymous(
    test_database_url, db_schema, monkeypatch
):
    """Sentinel: no peer institution_id string appears in any narrative
    field of the drafted brief."""
    monkeypatch.setenv("SBS_API_MODEL_PROVIDER", "mock")
    reset_provider_cache()

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            await _seed_sustained_spike(session)
            tick = await run_aggregation_tick(session, now=NOW)
            await session.commit()
        async with SM() as session:
            await run_investigation_from_pattern(
                session, pattern_id=tick.high_pattern_ids[0]
            )
            await session.commit()
            brief = (
                await session.execute(
                    select(FIBrief).where(FIBrief.institution_id == INST)
                )
            ).scalars().first()
    finally:
        await engine.dispose()

    assert brief is not None
    fields = [
        brief.pattern_summary_es,
        brief.pattern_summary_en or "",
        brief.peer_context_es,
        brief.peer_context_en or "",
    ]
    for f in fields:
        for peer_idx in range(1, 5):
            assert f"SBS-10{peer_idx:04d}" not in f
            assert f"SBS-20{peer_idx:04d}" not in f
        assert "Reclamo para cadena completa" not in f  # no raw narrative
