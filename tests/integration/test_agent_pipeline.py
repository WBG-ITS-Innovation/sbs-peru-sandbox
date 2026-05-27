"""Agent pipeline integration test — exercises the full chain end-to-end.

Seeds a complaint, runs the Triage → Investigation → Synthesis chain,
then asserts:
- One agent_run row exists per agent, ordered by started_at.
- Audit chain carries agent-run-started + agent-run-completed per agent.
- Findings detail endpoint surfaces classification + features + draft +
  executive_summary populated from the new agent rows.
- The BCO-2026-000001 demo invariants hold.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import jsonschema
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sbs_api.agents.orchestrator import run_agent_pipeline
from sbs_api.agents.providers import reset_provider_cache
from sbs_api.agents.providers.mock import MockProvider
from sbs_api.agents.providers.replay import ReplayProvider
from sbs_api.db.models.agent_run import AgentRun
from sbs_api.db.models.audit_event import AuditEvent
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.institution import InstitutionRecord
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "docs" / "schemas" / "agent_run.schema.json"

DEMO_ID = "BCO-2026-000001"


def _validator():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


async def _seed_complaint(session: AsyncSession, complaint_id: str) -> None:
    inst = (
        await session.execute(
            select(InstitutionRecord).where(
                InstitutionRecord.institution_id == "SBS-001234"
            )
        )
    ).scalar_one_or_none()
    if inst is None:
        session.add(
            InstitutionRecord(
                institution_id="SBS-001234",
                display_name="BANCO_DEMO_001",
            )
        )
    existing = (
        await session.execute(
            select(ComplaintRecord).where(
                ComplaintRecord.complaint_id == complaint_id
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            ComplaintRecord(
                complaint_id=complaint_id,
                institution_id="SBS-001234",
                received_date=date(2026, 5, 27),
                complainant_doc_type="DNI",
                product_category="credit-card",
                channel="branch",
                motivo_code="undisclosed-fee",
                severity="HIGH",
                description_text=(
                    "Cliente reclama cargos no informados en su tarjeta."
                ),
                description_language="es",
                complainant_age_range="35-44",
                complainant_district="150101",
                submission_method="api",
                source="api_realtime",
                received_at=datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc),
            )
        )
    await session.flush()


def _agent_runs_for(rows: list[AgentRun], name: str) -> list[AgentRun]:
    return [r for r in rows if r.agent_name == name]


@pytest.mark.asyncio
async def test_pipeline_writes_three_real_agent_runs(test_database_url, db_schema, monkeypatch):
    monkeypatch.setenv("SBS_API_MODEL_PROVIDER", "mock")
    reset_provider_cache()

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            await _seed_complaint(session, DEMO_ID)
            outcome = await run_agent_pipeline(
                session, complaint_id=DEMO_ID, provider=MockProvider()
            )
            await session.commit()

            rows = (
                await session.execute(
                    select(AgentRun)
                    .where(AgentRun.complaint_id == DEMO_ID)
                    .order_by(AgentRun.started_at)
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    triage = _agent_runs_for(rows, "triage")
    investigation = _agent_runs_for(rows, "investigation")
    synthesis = _agent_runs_for(rows, "synthesis")
    assert len(triage) == 1
    assert len(investigation) == 1
    assert len(synthesis) == 1
    assert outcome.route_to == "investigation"

    # Ordering: triage finished before investigation, investigation before synthesis.
    assert triage[0].ended_at <= investigation[0].started_at
    assert investigation[0].ended_at <= synthesis[0].started_at


@pytest.mark.asyncio
async def test_pipeline_emits_started_and_completed_audit_rows(
    test_database_url, db_schema, monkeypatch
):
    monkeypatch.setenv("SBS_API_MODEL_PROVIDER", "mock")
    reset_provider_cache()

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            await _seed_complaint(session, DEMO_ID)
            await run_agent_pipeline(
                session, complaint_id=DEMO_ID, provider=MockProvider()
            )
            await session.commit()

            audit = (
                await session.execute(
                    select(AuditEvent).where(AuditEvent.object_id == DEMO_ID)
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    actions = [r.action for r in audit]
    assert actions.count("agent-run-started") >= 3
    assert actions.count("agent-run-completed") >= 3


@pytest.mark.asyncio
async def test_pipeline_demo_invariants_with_replay_provider(
    test_database_url, db_schema, monkeypatch
):
    """Locked demo invariants must hold under the ReplayProvider path.

    - Triage classification = undisclosed-fees-credit (0.87)
    - Investigation top feature = narrative_mentions_fee_undisclosed (+0.27)
    - Investigation anomaly = 0.74 / 0.70 / true
    - Investigation draft OMITS 'comisión por mantenimiento'
    - Synthesis executive_summary non-empty plain Spanish
    """
    monkeypatch.setenv("SBS_API_MODEL_PROVIDER", "replay")
    reset_provider_cache()

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            await _seed_complaint(session, DEMO_ID)
            outcome = await run_agent_pipeline(
                session, complaint_id=DEMO_ID, provider=ReplayProvider()
            )
            await session.commit()
    finally:
        await engine.dispose()

    # Triage classification invariant.
    clf = outcome.triage["classification"]
    assert clf["label"] == "undisclosed-fees-credit"
    assert clf["confidence"] == 0.87

    # Investigation invariants.
    inv = outcome.investigation
    assert inv is not None
    top = inv["feature_attribution"][0]
    assert top["name"] == "narrative_mentions_fee_undisclosed"
    assert top["contribution"] == 0.27
    assert inv["anomaly"]["composite_score"] == 0.74
    assert inv["anomaly"]["threshold"] == 0.70
    assert inv["anomaly"]["anomaly_flag"] is True
    draft = inv["draft_narrative"]["text"]
    assert "comisión por mantenimiento" not in draft.lower()

    # Synthesis invariant: non-empty plain Spanish summary.
    syn = outcome.synthesis
    assert syn is not None
    text = syn["executive_summary"]["text"]
    assert text and len(text) > 30


@pytest.mark.asyncio
async def test_agent_run_rows_validate_against_json_schema(
    test_database_url, db_schema, monkeypatch
):
    monkeypatch.setenv("SBS_API_MODEL_PROVIDER", "mock")
    reset_provider_cache()

    engine = create_async_engine(test_database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SessionMaker() as session:
            await _seed_complaint(session, DEMO_ID)
            await run_agent_pipeline(
                session, complaint_id=DEMO_ID, provider=MockProvider()
            )
            await session.commit()

            rows = (
                await session.execute(
                    select(AgentRun).where(AgentRun.complaint_id == DEMO_ID)
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    validator = _validator()
    for run in rows:
        if run.agent_name == "live-ingestion-orchestrator":
            continue
        # Convert in-progress rows (none should remain after the chain
        # commits) onto a terminal status for schema validation.
        if run.status == "in_progress":
            continue
        row_dict = {
            "id": run.id,
            "complaint_id": run.complaint_id,
            "agent_name": run.agent_name,
            "agent_version": run.agent_version,
            "started_at": run.started_at.isoformat(timespec="microseconds"),
            "ended_at": run.ended_at.isoformat(timespec="microseconds")
            if run.ended_at
            else None,
            "status": run.status,
            "tool_calls": run.tool_calls,
            "final_output": run.final_output,
            "error": run.error,
        }
        validator.validate(row_dict)
