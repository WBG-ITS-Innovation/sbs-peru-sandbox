# SPDX-License-Identifier: Apache-2.0
"""DIValeVale Tier-2 batch routing (P-RESHAPE-8). DB-backed.

DEMO_BATCH_001: 6 VALID / 2 RECOVERABLE / 1 INSUFFICIENT / 1 INVALID →
QUARANTINED (INVALID present) → batch-rejection webhook → no rows to
Triage. Resubmit with corrected rows → ACCEPTED.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.agents.divalevale.agent import validate_tier2_batch
from sbs_api.agents.providers.mock import MockProvider
from sbs_api.db.models.validation_audit import ValidationBatch
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


def _row(i, **kw):
    base = {
        "complaint_id": f"BATCH-{i:03d}",
        "institution_code": "BCO_DEMO_001",
        "captured_at": "2026-05-27T10:00:00Z",
        "motivo_code": "CALIDAD_SERVICIO",
        "narrative_es": "Reclamo válido con narrativa suficientemente larga para pasar.",
    }
    base.update(kw)
    return base


def _demo_batch_001():
    rows = [_row(i) for i in range(6)]  # 6 VALID
    rows += [
        _row(
            6,
            motivo_code="COBRO_INDEBIDO",
            narrative_es="Me cobraron S/ 99.90 sin aviso, presento reclamo formal por ello.",
        ),
        _row(
            7,
            motivo_code="COBRO_INDEBIDO",
            narrative_es="Cargo de S/ 150.00 no reconocido en mi tarjeta, solicito reversa.",
        ),
    ]  # 2 RECOVERABLE (amount in narrative)
    rows += [_row(8, motivo_code="DEMORA_ATENCION", narrative_es="muy corto")]  # 1 INSUFFICIENT
    rows += [_row(9, motivo_code="NOT_A_MOTIVO")]  # 1 INVALID
    return rows


async def _ok(req: httpx.Request) -> tuple[int, str]:
    return 200, "ok"


@pytest.mark.asyncio
async def test_demo_batch_quarantines_on_invalid(test_database_url, db_schema):
    sent: list[str] = []

    async def capture(req: httpx.Request) -> tuple[int, str]:
        sent.append(req.headers.get("X-Payload-Type", ""))
        return 200, "ok"

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            res = await validate_tier2_batch(
                session,
                batch_id="DEMO_BATCH_001",
                records=_demo_batch_001(),
                sbs_institution_id="SBS-001234",
                institution_code="BCO_DEMO_001",
                provider=MockProvider(),
                sender=capture,
            )
            await session.commit()
    finally:
        await engine.dispose()

    assert res.decision.valid == 6
    assert res.decision.recoverable == 2
    assert res.decision.insufficient == 1
    assert res.decision.invalid == 1
    assert res.state == "QUARANTINED"
    assert res.decision.reason == "invalid_present"
    assert res.triage_eligible_records == []  # no rows reach Triage
    assert sent == ["VALIDATION_BATCH_REJECTION"]
    assert res.diagnostic_report is not None
    # Diagnostic carries codes only — no narrative text.
    blob = str(res.diagnostic_report)
    assert "narrativa" not in blob.lower()
    assert "cobraron" not in blob.lower()


@pytest.mark.asyncio
async def test_resubmit_same_batch_id_replaces_and_accepts(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            await validate_tier2_batch(
                session,
                batch_id="DEMO_BATCH_002",
                records=_demo_batch_001(),
                sbs_institution_id="SBS-001234",
                institution_code="BCO_DEMO_001",
                provider=MockProvider(),
                sender=_ok,
            )
            await session.commit()

            # Resubmit with all-valid rows under the same batch_id.
            res = await validate_tier2_batch(
                session,
                batch_id="DEMO_BATCH_002",
                records=[_row(i) for i in range(6)],
                sbs_institution_id="SBS-001234",
                institution_code="BCO_DEMO_001",
                provider=MockProvider(),
                sender=_ok,
            )
            await session.commit()

            batches = (
                await session.execute(
                    select(ValidationBatch).where(
                        ValidationBatch.batch_id == "DEMO_BATCH_002"
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()
    assert res.state == "ACCEPTED"
    assert len(res.triage_eligible_records) == 6
    # The current row reflects ACCEPTED (prior quarantined state replaced).
    assert batches[-1].state in ("ACCEPTED", "REPLACED")


@pytest.mark.asyncio
async def test_low_insufficient_no_invalid_accepts(test_database_url, db_schema):
    # 6 valid + 1 insufficient (< 20%, no invalid) → ACCEPTED.
    rows = [_row(i) for i in range(6)]
    rows.append(_row(6, motivo_code="DEMORA_ATENCION", narrative_es="corto"))
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            res = await validate_tier2_batch(
                session, batch_id="B-ACCEPT", records=rows,
                sbs_institution_id="SBS-001234", institution_code="BCO_DEMO_001",
                provider=MockProvider(), sender=_ok,
            )
            await session.commit()
    finally:
        await engine.dispose()
    assert res.state == "ACCEPTED"
    assert len(res.triage_eligible_records) == 6
