# SPDX-License-Identifier: Apache-2.0
"""DIValeVale full-chain integration (P-RESHAPE-8). DB-backed.

Asserts the pipeline ordering (DIValeVale BEFORE Triage) via the stage
trace, and that an INSUFFICIENT record never reaches Triage while a
VALID one does. Also exercises the Tier-2 batch quarantine end-to-end.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.agents.divalevale.agent import validate_tier2_batch
from sbs_api.agents.providers.mock import MockProvider
from sbs_api.db.models.validation_audit import ValidationAudit, ValidationBatch
from sbs_api.ingestion.pipeline import run_tier1_ingestion
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


async def _ok(req: httpx.Request) -> tuple[int, str]:
    return 200, "ok"


def _valid_rec():
    return {
        "complaint_id": "BCO-2026-000001",  # exists in db_schema seed (FK-safe for triage)
        "institution_code": "BCO_DEMO_001",
        "captured_at": "2026-05-27T10:00:00Z",
        "motivo_code": "CALIDAD_SERVICIO",
        "narrative_es": "Reclamo con narrativa suficientemente larga para validar.",
    }


@pytest.mark.asyncio
async def test_pipeline_runs_divalevale_before_triage(test_database_url, db_schema, monkeypatch):
    monkeypatch.setenv("SBS_API_MODEL_PROVIDER", "mock")
    from sbs_api.agents.providers import reset_provider_cache

    reset_provider_cache()
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            trace = await run_tier1_ingestion(
                session,
                record=_valid_rec(),
                sbs_institution_id="SBS-001234",
                provider=MockProvider(),
                sender=_ok,
                run_triage=True,
            )
            await session.commit()
    finally:
        await engine.dispose()

    # Ordering: divalevale strictly before triage.
    assert "divalevale" in trace.stages
    assert "triage" in trace.stages
    assert trace.stages.index("divalevale") < trace.stages.index("triage")
    assert trace.reached_triage is True
    assert trace.validation.verdict == "VALID"


@pytest.mark.asyncio
async def test_insufficient_never_reaches_triage(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            trace = await run_tier1_ingestion(
                session,
                record={
                    "complaint_id": "BCO-2026-000004",
                    "institution_code": "BCO_DEMO_001",
                    "captured_at": "2026-05-27T10:00:00Z",
                    "motivo_code": "COBRO_INDEBIDO",
                    "narrative_es": "se me cobró mal",
                },
                sbs_institution_id="SBS-001234",
                provider=MockProvider(),
                sender=_ok,
            )
            await session.commit()
    finally:
        await engine.dispose()
    assert trace.stages == ["divalevale"]  # never advanced to triage
    assert trace.reached_triage is False
    assert trace.validation.routing_action == "FLAGGED_FOR_ENRICHMENT"


@pytest.mark.asyncio
async def test_tier2_demo_batch_quarantines_no_triage(test_database_url, db_schema):
    rows = [
        {
            "complaint_id": f"DB1-{i:03d}",
            "institution_code": "BCO_DEMO_001",
            "captured_at": "2026-05-27T10:00:00Z",
            "motivo_code": "CALIDAD_SERVICIO",
            "narrative_es": "Narrativa válida suficientemente larga para el lote.",
        }
        for i in range(6)
    ] + [
        {"complaint_id": "DB1-009", "institution_code": "BCO_DEMO_001",
         "captured_at": "2026-05-27T10:00:00Z", "motivo_code": "NOT_A_MOTIVO",
         "narrative_es": "x" * 40},
    ]
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            res = await validate_tier2_batch(
                session, batch_id="DEMO_BATCH_CHAIN", records=rows,
                sbs_institution_id="SBS-001234", institution_code="BCO_DEMO_001",
                provider=MockProvider(), sender=_ok,
            )
            await session.commit()
            audits = (
                await session.execute(
                    select(ValidationAudit).where(
                        ValidationAudit.batch_id == "DEMO_BATCH_CHAIN"
                    )
                )
            ).scalars().all()
            batch = (
                await session.execute(
                    select(ValidationBatch).where(
                        ValidationBatch.batch_id == "DEMO_BATCH_CHAIN"
                    )
                )
            ).scalar_one()
    finally:
        await engine.dispose()
    assert res.state == "QUARANTINED"  # 1 INVALID present
    assert res.triage_eligible_records == []
    assert batch.invalid_count == 1
    assert len(audits) == 7  # one audit row per evaluated row
