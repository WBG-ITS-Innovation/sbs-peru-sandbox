"""End-to-end pattern-aggregation → Investigation integration test.

Seeds a fresh corpus on top of the ``db_schema`` baseline so the
aggregation tick has data to detect against:

* BANCO_DEMO_001 / category=CALIDAD_SERVICIO: 8 in 24h vs 1.0 daily
  baseline → fires VOLUME_SPIKE.
* COOPAC_DEMO_002 / category=OPERACION_NO_RECONOCIDA: 12 in 7d vs 6
  prior 7d, with 4 INDECOPI cases in 7d vs 2 prior → fires
  CROSS_SOURCE_CORRELATION.

After the tick, asserts:
1. Two HIGH ``pattern_detections`` rows are present.
2. Both VOLUME_SPIKE and CROSS_SOURCE_CORRELATION fired.
3. ``run_investigation_from_pattern`` for each fires Investigation and
   writes an ``agent_runs`` row whose ``final_output.trigger_source``
   is ``PATTERN`` and whose ``pattern_id`` matches the row.
4. ``triggered_investigation`` is True + ``investigation_run_id`` is
   set on the pattern row after Investigation fires.
5. Re-running the tick + the orchestrator path is idempotent: no
   additional Investigation runs, no duplicate pattern rows.
6. PII-sentinel invariant: the persisted pattern carries IDs only
   (no narrative text leaks into ``contributing_complaint_ids`` or
   ``composite_breakdown``).

DB-gated via ``pytestmark_db``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.aggregation.tick import run_aggregation_tick
from sbs_api.agents.orchestrator import run_investigation_from_pattern
from sbs_api.db.models.agent_run import AgentRun
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.indecopi_case import IndecopiCase
from sbs_api.db.models.pattern_detection import PatternDetection
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


NOW = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)

SPIKE_INSTITUTION = "SBS-001234"  # BANCO_DEMO_001
SPIKE_CATEGORY = "CALIDAD_SERVICIO"

CROSS_INSTITUTION = "SBS-005678"  # COOPAC_DEMO_002
CROSS_CATEGORY = "OPERACION_NO_RECONOCIDA"


def _complaint(
    complaint_id: str,
    institution_id: str,
    motivo_code: str,
    received_at: datetime,
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
        description_text="Seed para integración pattern→Investigation.",
        description_language="es",
        complainant_age_range="35_44",
        complainant_district="150100",
        submission_method="APP_MOVIL",
        original_reference_id=None,
        resolution_status="pendiente",
        source="api_realtime",
        received_at=received_at,
    )


async def _seed_pattern_corpus(session) -> None:
    # VOLUME_SPIKE: 8 complaints in last 24h, 7 in prior 7d → daily
    # mean 1.0. All complaints offset >= 1 hour from boundaries so
    # the test does not depend on window boundary semantics.
    for i in range(8):
        session.add(
            _complaint(
                f"SPK-2026-{i:06d}",
                SPIKE_INSTITUTION,
                SPIKE_CATEGORY,
                NOW - timedelta(hours=2 + i),
            )
        )
    for i in range(7):
        session.add(
            _complaint(
                f"SPK-PRIOR-{i:06d}",
                SPIKE_INSTITUTION,
                SPIKE_CATEGORY,
                NOW - timedelta(days=1, hours=12) - timedelta(days=i),
            )
        )

    # CROSS_SOURCE_CORRELATION: 12 complaints in last 7d, 6 in prior
    # 7d (WoW 2.0x), 4 INDECOPI cases in 7d vs 2 prior (WoW 2.0x).
    # Distribute the 12 across the 7-day window so the 24h count stays
    # below VOLUME_SPIKE's floor of 3 — we want CROSS_SOURCE only.
    cross_complaint_ids = []
    for i in range(12):
        # offset cleanly inside [now-7d, now), no item in the last 24h
        # to avoid co-firing VOLUME_SPIKE.
        offset_hours = 30 + i * 12  # 30h, 42h, ... 162h ≈ 6.75 days
        cid = f"CSR-2026-{i:06d}"
        cross_complaint_ids.append(cid)
        session.add(
            _complaint(
                cid,
                CROSS_INSTITUTION,
                CROSS_CATEGORY,
                NOW - timedelta(hours=offset_hours),
            )
        )
    for i in range(6):
        session.add(
            _complaint(
                f"CSR-PRIOR-{i:06d}",
                CROSS_INSTITUTION,
                CROSS_CATEGORY,
                NOW - timedelta(days=8) - timedelta(hours=i * 12),
            )
        )

    for i in range(4):
        session.add(
            IndecopiCase(
                case_id=f"INDE-7D-{i}",
                institution_id=CROSS_INSTITUTION,
                complaint_category=CROSS_CATEGORY,
                opened_at=NOW - timedelta(days=1 + i),
                summary="INDECOPI cross-source corroborating case.",
            )
        )
    for i in range(2):
        session.add(
            IndecopiCase(
                case_id=f"INDE-PRIOR-{i}",
                institution_id=CROSS_INSTITUTION,
                complaint_category=CROSS_CATEGORY,
                opened_at=NOW - timedelta(days=10 + i),
            )
        )
    await session.flush()


@pytest.mark.asyncio
async def test_tick_emits_two_high_patterns_and_investigation_fires_twice(
    test_database_url, db_schema
):
    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            await _seed_pattern_corpus(session)

            tick = await run_aggregation_tick(session, now=NOW)
            await session.commit()

            high_rows = (
                await session.execute(
                    select(PatternDetection).where(
                        PatternDetection.severity_band == "HIGH"
                    )
                )
            ).scalars().all()

        async with SessionMaker() as session:
            # Fire Investigation for each new HIGH pattern.
            investigation_outputs = []
            for pid in tick.high_pattern_ids:
                out = await run_investigation_from_pattern(
                    session, pattern_id=pid
                )
                investigation_outputs.append(out)
            await session.commit()

            agent_rows = (
                await session.execute(
                    select(AgentRun).where(AgentRun.agent_name == "investigation")
                )
            ).scalars().all()
            patterns_after = (
                await session.execute(select(PatternDetection))
            ).scalars().all()
    finally:
        await engine.dispose()

    # 2 HIGH patterns total — one VOLUME_SPIKE, one CROSS_SOURCE_CORRELATION.
    assert len(high_rows) == 2
    pattern_types = {r.pattern_type for r in high_rows}
    assert pattern_types == {"VOLUME_SPIKE", "CROSS_SOURCE_CORRELATION"}

    # 2 Investigation outputs, both with PATTERN trigger.
    assert len(investigation_outputs) == 2
    assert all(out["trigger_source"] == "PATTERN" for out in investigation_outputs)
    assert {out["pattern_id"] for out in investigation_outputs} == {
        r.pattern_id for r in high_rows
    }

    # Every pattern row is now triggered + linked to its run.
    triggered = [p for p in patterns_after if p.severity_band == "HIGH"]
    assert all(p.triggered_investigation for p in triggered)
    assert all(p.investigation_run_id is not None for p in triggered)

    # 2 Investigation agent_runs (matches the two PATTERN fires). Each
    # uses the pattern's first contributing complaint as anchor.
    pattern_runs = [r for r in agent_rows if (r.final_output or {}).get("trigger_source") == "PATTERN"]
    assert len(pattern_runs) == 2


@pytest.mark.asyncio
async def test_repeat_tick_is_idempotent_no_extra_investigation_runs(
    test_database_url, db_schema
):
    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            await _seed_pattern_corpus(session)

            first = await run_aggregation_tick(session, now=NOW)
            for pid in first.high_pattern_ids:
                await run_investigation_from_pattern(session, pattern_id=pid)
            await session.commit()

            # Second tick — same data, same NOW. No new patterns,
            # nothing for run_investigation_from_pattern to do.
            second = await run_aggregation_tick(session, now=NOW)
            await session.commit()

            pattern_rows = (
                await session.execute(select(PatternDetection))
            ).scalars().all()
            agent_rows = (
                await session.execute(
                    select(AgentRun).where(AgentRun.agent_name == "investigation")
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    assert second.rows_inserted == 0
    assert second.rows_reused == first.candidates_evaluated
    # No new pattern rows.
    assert len(pattern_rows) == first.candidates_evaluated
    # First-tick fires landed exactly 2 PATTERN Investigation runs; the
    # second tick must not have added more.
    pattern_runs = [r for r in agent_rows if (r.final_output or {}).get("trigger_source") == "PATTERN"]
    assert len(pattern_runs) == 2


@pytest.mark.asyncio
async def test_double_fire_prevention_via_advisory_lock(
    test_database_url, db_schema
):
    """Calling :func:`run_investigation_from_pattern` twice for the
    same pattern_id must produce exactly one Investigation row. The
    advisory lock + the persisted ``triggered_investigation`` flag are
    the two layers of defence."""
    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            await _seed_pattern_corpus(session)
            tick = await run_aggregation_tick(session, now=NOW)
            assert tick.high_pattern_ids
            first_id = tick.high_pattern_ids[0]
            await session.commit()

        async with SessionMaker() as session:
            first = await run_investigation_from_pattern(session, pattern_id=first_id)
            await session.commit()
            second = await run_investigation_from_pattern(session, pattern_id=first_id)
            await session.commit()

            agent_rows = (
                await session.execute(
                    select(AgentRun).where(AgentRun.agent_name == "investigation")
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    assert first is not None
    assert second is None  # second call short-circuits
    pattern_runs_for_this = [
        r
        for r in agent_rows
        if (r.final_output or {}).get("pattern_id") == first_id
    ]
    assert len(pattern_runs_for_this) == 1


@pytest.mark.asyncio
async def test_pattern_payload_carries_ids_not_narrative_text(
    test_database_url, db_schema
):
    """PII sentinel: ``pattern_detections`` rows must reference
    complaint IDs and INDECOPI case IDs only — never raw narrative."""
    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            await _seed_pattern_corpus(session)
            await run_aggregation_tick(session, now=NOW)
            await session.commit()

            rows = (
                await session.execute(select(PatternDetection))
            ).scalars().all()
    finally:
        await engine.dispose()

    needle = "Seed para integración"  # appears in every seeded narrative
    for row in rows:
        for cid in row.contributing_complaint_ids:
            assert needle not in cid
        for case_id in row.contributing_indecopi_case_ids or []:
            assert needle not in case_id
        # composite_breakdown is JSON; the serialised text must not
        # leak the narrative either.
        import json

        as_text = json.dumps(row.composite_breakdown)
        assert needle not in as_text
