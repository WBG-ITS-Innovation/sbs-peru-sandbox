"""Windower — rolling counts read from the canonical complaints table.

The detector tests cover the rule predicates directly. This file
covers the SQL-layer translation: the windower must group complaints
by (institution_id, motivo_code), bucket them into 24h / 7d / 30d
windows relative to a given ``now``, compute prior-mean daily / weekly
counts, and join in INDECOPI cases for the cross-source rule.

Uses the standard ``db_schema`` testcontainer fixture so the SQL runs
against real Postgres (not SQLite). DB-gated via ``pytestmark_db``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.aggregation.windower import build_windows
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.indecopi_case import IndecopiCase
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


NOW = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)


async def _seed_spike_bucket(
    session, *, institution_id: str, category: str, prefix: str
) -> None:
    """Seed the canonical VOLUME_SPIKE shape: 8 in 24h, daily mean 1.0
    over the prior 7 days (so 7 in [now-8d, now-1d])."""
    for i in range(8):
        session.add(
            _complaint(
                f"{prefix}-S-{i:06d}",
                institution_id,
                category,
                NOW - timedelta(hours=2 + i * 1),
            )
        )
    # Seed each prior-window complaint 12 hours past the prior bucket
    # boundary so the test does not depend on whether the windower
    # treats the boundary as inclusive or exclusive — they all sit
    # strictly inside (NOW-8d, NOW-1d].
    for i in range(7):
        session.add(
            _complaint(
                f"{prefix}-P-{i:06d}",
                institution_id,
                category,
                NOW - timedelta(days=1, hours=12) - timedelta(days=i),
            )
        )
    await session.flush()


def _complaint(
    complaint_id: str, institution_id: str, motivo_code: str, received_at: datetime
) -> ComplaintRecord:
    return ComplaintRecord(
        complaint_id=complaint_id,
        institution_id=institution_id,
        received_date=received_at.date(),
        complainant_doc_type="DNI",
        product_category="TARJETA_CREDITO",
        channel="APP_MOVIL",
        motivo_code=motivo_code,
        severity="HIGH",
        description_text="Reclamo de prueba para windower.",
        description_language="es",
        complainant_age_range="35_44",
        complainant_district="150100",
        submission_method="APP_MOVIL",
        original_reference_id=None,
        resolution_status="pendiente",
        source="api_realtime",
        received_at=received_at,
    )


@pytest.mark.asyncio
async def test_24h_bucket_counts_spike_correctly(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            await _seed_spike_bucket(
                session,
                institution_id="SBS-001234",
                category="CALIDAD_SERVICIO",
                prefix="WND",
            )
            windows = await build_windows(session, now=NOW)
    finally:
        await engine.dispose()

    bucket = next(
        w for w in windows
        if w.institution_id == "SBS-001234"
        and w.complaint_category == "CALIDAD_SERVICIO"
    )
    assert bucket.count_24h == 8
    # 7 in the prior-7d window → daily mean exactly 1.0.
    assert bucket.prior_7d_daily_mean == pytest.approx(1.0)
    # No INDECOPI cases seeded — both counts stay zero.
    assert bucket.indecopi_count_7d == 0
    assert bucket.indecopi_count_7d_prior == 0
    assert len(bucket.contributing_complaint_ids_24h) == 8


@pytest.mark.asyncio
async def test_indecopi_cases_are_picked_up_per_bucket(
    test_database_url, db_schema
):
    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            # Single complaint to make the bucket exist.
            session.add(
                _complaint(
                    "IND-2026-000001",
                    "SBS-005678",
                    "OPERACION_NO_RECONOCIDA",
                    NOW - timedelta(days=2),
                )
            )
            # 4 INDECOPI cases in 7d, 2 in prior 7d.
            for i in range(4):
                session.add(
                    IndecopiCase(
                        case_id=f"IND-7D-{i}",
                        institution_id="SBS-005678",
                        complaint_category="OPERACION_NO_RECONOCIDA",
                        opened_at=NOW - timedelta(days=1 + i),
                    )
                )
            for i in range(2):
                session.add(
                    IndecopiCase(
                        case_id=f"IND-PRIOR-{i}",
                        institution_id="SBS-005678",
                        complaint_category="OPERACION_NO_RECONOCIDA",
                        opened_at=NOW - timedelta(days=10 + i),
                    )
                )
            await session.flush()
            windows = await build_windows(session, now=NOW)
    finally:
        await engine.dispose()

    bucket = next(
        w for w in windows
        if w.institution_id == "SBS-005678"
        and w.complaint_category == "OPERACION_NO_RECONOCIDA"
    )
    assert bucket.indecopi_count_7d == 4
    assert bucket.indecopi_count_7d_prior == 2
    assert len(bucket.contributing_indecopi_case_ids_7d) == 4
