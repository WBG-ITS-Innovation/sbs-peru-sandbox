"""Pattern → Investigation → PRR → narrative-v1 dossier integration test.

Seeds the VOLUME_SPIKE corpus from test_pattern_to_investigation,
runs the aggregation tick, fires Investigation from pattern, and
asserts the dossier was upgraded to narrative-v1 with PRR analysis
merged in.

DB-gated via ``pytestmark_db``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.aggregation.tick import run_aggregation_tick
from sbs_api.agents.orchestrator import run_investigation_from_pattern
from sbs_api.agents.providers import reset_provider_cache
from sbs_api.db.models.agent_run import AgentRun
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.peer_risk_analysis import PeerRiskAnalysis
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

NOW = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
SPIKE_INSTITUTION = "SBS-001234"
SPIKE_CATEGORY = "CALIDAD_SERVICIO"


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
        description_text="Reclamo para integración PRR end-to-end.",
        description_language="es",
        complainant_age_range="35_44",
        complainant_district="150100",
        submission_method="APP_MOVIL",
        resolution_status="pendiente",
        source="api_realtime",
        received_at=received_at,
    )


async def _seed_spike_plus_peers(session) -> None:
    # 8 BANCO spike complaints in last 24h.
    for i in range(8):
        session.add(
            _complaint(
                f"PRR-E2E-S-{i:06d}",
                SPIKE_INSTITUTION,
                SPIKE_CATEGORY,
                NOW - timedelta(hours=2 + i),
            )
        )
    # 7 prior-window for baseline.
    for i in range(7):
        session.add(
            _complaint(
                f"PRR-E2E-P-{i:06d}",
                SPIKE_INSTITUTION,
                SPIKE_CATEGORY,
                NOW - timedelta(days=1, hours=12) - timedelta(days=i),
            )
        )
    # Peer complaints so percentile computation is meaningful.
    for peer_idx in range(1, 5):
        peer_id = f"SBS-10{peer_idx:04d}"
        for j in range(2):
            session.add(
                _complaint(
                    f"PRR-E2E-PEER-{peer_idx}-{j:06d}",
                    peer_id,
                    SPIKE_CATEGORY,
                    NOW - timedelta(days=1 + j),
                )
            )
    await session.flush()


@pytest.mark.asyncio
async def test_pattern_investigation_produces_narrative_v1_dossier(
    test_database_url, db_schema, monkeypatch
):
    monkeypatch.setenv("SBS_API_MODEL_PROVIDER", "mock")
    reset_provider_cache()

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            await _seed_spike_plus_peers(session)
            tick = await run_aggregation_tick(session, now=NOW)
            await session.commit()

        high_ids = [pid for pid in tick.high_pattern_ids]
        # At least 1 HIGH pattern (VOLUME_SPIKE on BANCO).
        assert len(high_ids) >= 1

        async with SM() as session:
            dossier = await run_investigation_from_pattern(
                session, pattern_id=high_ids[0]
            )
            await session.commit()

            prr_rows = (
                await session.execute(select(PeerRiskAnalysis))
            ).scalars().all()

            inv_runs = (
                await session.execute(
                    select(AgentRun).where(AgentRun.agent_name == "investigation")
                )
            ).scalars().all()
            prr_runs = (
                await session.execute(
                    select(AgentRun).where(AgentRun.agent_name == "peer-risk-radar")
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    # Dossier upgraded to narrative-v1.
    assert dossier is not None
    assert dossier["dossier_format"] == "narrative-v1"
    assert dossier["trigger_source"] == "PATTERN"

    # PRR analysis block is merged into the dossier.
    prr = dossier["peer_risk_analysis"]
    assert prr["cohort_id"] == "BANCO:TIER_1"
    assert prr["narrative_es"]
    assert len(prr["narrative_es"]) > 20
    # Model provenance recorded.
    assert prr["model_id"]
    assert prr["model_provider"] in {"onprem", "mock", "template"}

    # Each model's ID is preserved — Investigation's own evidence block
    # still carries "pattern-aggregation-v1" and the PRR block carries
    # the PRR model_id.
    assert dossier["anomaly"]["model_id"] == "pattern-aggregation-v1"
    assert prr["model_id"] != dossier["anomaly"]["model_id"]

    # Storage: 1 peer_risk_analyses row.
    assert len(prr_rows) == 1
    assert prr_rows[0].pattern_id == high_ids[0]

    # Agent runs: 1 investigation + 1 peer-risk-radar.
    pattern_inv = [r for r in inv_runs if (r.final_output or {}).get("trigger_source") == "PATTERN"]
    assert len(pattern_inv) == 1
    assert len(prr_runs) == 1


@pytest.mark.asyncio
async def test_prr_percentile_shows_banco_as_outlier(
    test_database_url, db_schema, monkeypatch
):
    """BANCO_DEMO_001 volume_spike with 8 complaints vs peers at ~2
    each should land above the 90th percentile."""
    monkeypatch.setenv("SBS_API_MODEL_PROVIDER", "mock")
    reset_provider_cache()

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            await _seed_spike_plus_peers(session)
            tick = await run_aggregation_tick(session, now=NOW)
            await session.commit()

        async with SM() as session:
            dossier = await run_investigation_from_pattern(
                session, pattern_id=tick.high_pattern_ids[0]
            )
            await session.commit()
    finally:
        await engine.dispose()

    prr = dossier["peer_risk_analysis"]
    assert prr["is_outlier"] is True
    assert prr["percentile"] is not None
    assert prr["percentile"] >= 90.0
