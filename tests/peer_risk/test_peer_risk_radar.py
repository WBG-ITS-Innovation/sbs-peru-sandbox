"""PRR agent tests — cloud rejection, template fallback, PII sentinel.

Uses MockProvider (which returns canned text) for the LLM call.
The mock text is not valid JSON so the template fallback always fires
in these unit-level tests — that is intentional; the LLM-happy-path
is tested in the integration test where a mini stub provider returns
well-formed JSON.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.agents.investigation import PatternContext
from sbs_api.agents.peer_risk_radar import (
    MODEL_ID_TEMPLATE_FALLBACK,
    run_peer_risk_radar,
)
from sbs_api.agents.providers.mock import MockProvider
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.pattern_detection import PatternDetection
from sbs_api.db.models.peer_risk_analysis import PeerRiskAnalysis
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

NOW = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
PATTERN_ID = "test-pattern-prr-001"


async def _seed_pattern_row(session, *, contributing_ids: list[str]) -> None:
    """PeerRiskAnalysis FKs to pattern_detections — seed the parent row
    so the agent's persistence succeeds."""
    session.add(
        PatternDetection(
            pattern_id=PATTERN_ID,
            detected_at=NOW,
            window_start=NOW - timedelta(hours=24),
            window_end=NOW,
            institution_code="SBS-001234",
            complaint_category="CALIDAD_SERVICIO",
            pattern_type="VOLUME_SPIKE",
            severity_score=0.72,
            severity_band="HIGH",
            contributing_complaint_ids=contributing_ids,
            contributing_indecopi_case_ids=None,
            composite_breakdown={"weights": {}, "sub_scores": {}},
            triggered_investigation=False,
            investigation_run_id=None,
        )
    )
    await session.flush()


def _seeded_id(institution_id: str, i: int) -> str:
    return f"PRR-{institution_id[-4:]}-{i:06d}"


def _pattern(institution_id: str = "SBS-001234", category: str = "CALIDAD_SERVICIO") -> PatternContext:
    # Anchor on complaint IDs the test actually seeds (the agent_run row
    # has an FK to complaints.complaint_id).
    return PatternContext(
        pattern_id=PATTERN_ID,
        pattern_type="VOLUME_SPIKE",
        severity_score=0.72,
        severity_band="HIGH",
        institution_id=institution_id,
        complaint_category=category,
        contributing_complaint_ids=[
            _seeded_id(institution_id, 0),
            _seeded_id(institution_id, 1),
        ],
        contributing_indecopi_case_ids=[],
        composite_breakdown={"weights": {}, "sub_scores": {}},
    )


async def _seed_peer_complaints(session, *, institution_id: str, category: str, count: int) -> None:
    for i in range(count):
        session.add(
            ComplaintRecord(
                complaint_id=_seeded_id(institution_id, i),
                institution_id=institution_id,
                received_date=date(2026, 5, 20 + (i % 7)),
                complainant_doc_type="DNI",
                product_category="TARJETA_CREDITO",
                channel="APP_MOVIL",
                motivo_code=category,
                severity="HIGH",
                description_text="Reclamo de peer para PRR.",
                description_language="es",
                complainant_age_range="35_44",
                complainant_district="150100",
                submission_method="APP_MOVIL",
                resolution_status="pendiente",
                source="api_realtime",
                received_at=NOW - timedelta(days=1 + (i % 5)),
            )
        )
    await session.flush()


@pytest.mark.asyncio
async def test_prr_produces_template_narrative_on_mock_provider(
    test_database_url, db_schema
):
    """MockProvider returns non-JSON text → template fallback fires.
    Verifies: analysis row persisted, narratives non-empty, model_id
    reflects the fallback."""
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            await _seed_peer_complaints(session, institution_id="SBS-001234", category="CALIDAD_SERVICIO", count=8)
            for peer_id in [f"SBS-10{i:04d}" for i in range(1, 5)]:
                await _seed_peer_complaints(session, institution_id=peer_id, category="CALIDAD_SERVICIO", count=2)
            await _seed_pattern_row(
                session, contributing_ids=[_seeded_id("SBS-001234", 0), _seeded_id("SBS-001234", 1)]
            )
            result = await run_peer_risk_radar(
                session, pattern=_pattern(), provider=MockProvider(), now=NOW
            )
            await session.commit()

            row = (
                await session.execute(
                    select(PeerRiskAnalysis).where(
                        PeerRiskAnalysis.analysis_id == result.analysis_id
                    )
                )
            ).scalar_one()
    finally:
        await engine.dispose()

    assert result.model_id == MODEL_ID_TEMPLATE_FALLBACK
    assert result.model_provider == "template"
    assert result.narrative_es
    assert len(result.narrative_es) > 30
    assert result.narrative_en
    assert result.cohort_id == "BANCO:TIER_1"
    assert row.narrative_es == result.narrative_es


@pytest.mark.asyncio
async def test_prr_rejects_cloud_provider(test_database_url, db_schema):
    """Cloud provider is blocked for PRR in v1. Raises RuntimeError."""
    from sbs_api.agents.providers.cloud import CloudProvider
    import os

    os.environ["SBS_API_CLOUD_LEGAL_APPROVED"] = "true"
    try:
        cloud = CloudProvider()
    except NotImplementedError:
        pytest.skip("CloudProvider itself raises — the gate is upstream")
        return
    finally:
        os.environ.pop("SBS_API_CLOUD_LEGAL_APPROVED", None)

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            with pytest.raises(RuntimeError, match="on-prem"):
                await run_peer_risk_radar(
                    session, pattern=_pattern(), provider=cloud, now=NOW
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_prr_narrative_does_not_leak_raw_narrative_text(
    test_database_url, db_schema
):
    """PII sentinel: the PRR narrative must reference IDs and category
    names, never raw complaint text."""
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            await _seed_peer_complaints(session, institution_id="SBS-001234", category="CALIDAD_SERVICIO", count=5)
            await _seed_pattern_row(
                session, contributing_ids=[_seeded_id("SBS-001234", 0), _seeded_id("SBS-001234", 1)]
            )
            result = await run_peer_risk_radar(
                session, pattern=_pattern(), provider=MockProvider(), now=NOW
            )
            await session.commit()
    finally:
        await engine.dispose()

    needle = "Reclamo de peer para PRR"
    assert needle not in result.narrative_es
    assert needle not in (result.narrative_en or "")
