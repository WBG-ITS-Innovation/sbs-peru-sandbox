# SPDX-License-Identifier: Apache-2.0
"""stage-h-contract — the agent layer is wired into canonical ingestion.

Contract-level companion to ``scripts/smoke_stage_h_live.py``
(stage-h-full). These assertions run in-process against the
testcontainer Postgres; the live gate re-proves the same wiring over
real TLS, Redis and the worker container.

What is pinned here is the wiring that was missing, not the agents'
behaviour (covered by tests/test_agent_*.py):

* both ingestion tiers dispatch the chain,
* DIValeVale runs ahead of Triage and records one validation_audit row,
* the dispatch layer cannot break the ingesting request,
* the record adapter invents no fields.
"""

from __future__ import annotations

import inspect

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.agents.dispatch import dispatch_agent_pipeline
from sbs_api.agents.ingest_entry import (
    canonical_record_to_validation_record,
    run_agents_for_complaint,
)
from sbs_api.db.models.agent_run import AgentRun
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.validation_audit import ValidationAudit
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

SEEDED_COMPLAINT = "BCO-2026-000001"


# --- wiring: both tiers reach the dispatcher -------------------------------


def test_tier1_route_dispatches_the_agent_chain():
    """POST /v1/complaints hands the committed complaint to the dispatcher.

    Before this wiring the route had no agent call site at all, so
    SBS_API_AGENTS_PIPELINE_ENABLED had no effect on Tier 1.
    """
    from sbs_api.routes import complaints

    source = inspect.getsource(complaints.create_complaint)
    assert "dispatch_agent_pipeline" in source, (
        "POST /v1/complaints must hand the complaint to the agent dispatcher"
    )
    assert "BackgroundTask(" in source, (
        "dispatch must be attached as a background task so it cannot slow "
        "or fail the 201"
    )


def test_tier2_worker_dispatches_the_agent_chain():
    """The arq worker runs the chain over accepted rows itself."""
    from sbs_api.workers import batch_worker

    source = inspect.getsource(batch_worker.process_batch)
    assert "dispatch_agent_pipeline" in source, (
        "the batch worker must run the agent chain over accepted rows "
        "instead of relying on scripts/run_agent_pipeline_on_new.py"
    )


# --- the dispatcher cannot break the ingesting request ---------------------


@pytest.mark.asyncio
async def test_dispatch_is_a_noop_when_the_pipeline_is_disabled(monkeypatch):
    from sbs_api.config import get_settings

    monkeypatch.setenv("SBS_API_AGENTS_PIPELINE_ENABLED", "false")
    get_settings.cache_clear()
    try:
        # No DB configured for this call: if it were not a no-op it would
        # raise rather than return.
        await dispatch_agent_pipeline("BCO-2026-000404", tier="tier1")
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_dispatch_swallows_failures(monkeypatch):
    """A broken chain must never propagate to the ingesting request."""
    from sbs_api.config import get_settings

    monkeypatch.setenv("SBS_API_AGENTS_PIPELINE_ENABLED", "true")
    get_settings.cache_clear()
    try:
        # An unknown complaint_id makes run_agents_for_complaint raise;
        # dispatch must absorb it.
        await dispatch_agent_pipeline("BCO-2026-999999", tier="tier1")
    finally:
        get_settings.cache_clear()


# --- DIValeVale runs ahead of Triage --------------------------------------


@pytest.mark.asyncio
async def test_divalevale_runs_before_triage_and_records_one_audit_row(
    test_database_url, db_schema
):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            outcome = await run_agents_for_complaint(
                session, complaint_id=SEEDED_COMPLAINT
            )
            await session.commit()

        async with SM() as session:
            audits = (
                await session.execute(
                    select(ValidationAudit).where(
                        ValidationAudit.complaint_id == SEEDED_COMPLAINT
                    )
                )
            ).scalars().all()
            runs = (
                await session.execute(
                    select(AgentRun)
                    .where(AgentRun.complaint_id == SEEDED_COMPLAINT)
                    .order_by(AgentRun.started_at)
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    assert len(audits) == 1, (
        f"expected exactly one validation_audit row, got {len(audits)}"
    )
    assert audits[0].tier == "TIER_1"
    assert outcome.validation_verdict is not None
    assert outcome.validation_audit_id == audits[0].audit_id

    triage = [r for r in runs if r.agent_name == "triage"]
    assert triage, "triage must still run after the validation stage"
    # Ordering: the audit row is written before the first agent_run starts.
    assert audits[0].received_at <= triage[0].started_at


@pytest.mark.asyncio
async def test_provider_identity_is_persisted(test_database_url, db_schema):
    """agent_runs.model_provider records who actually served the call."""
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            await run_agents_for_complaint(
                session, complaint_id=SEEDED_COMPLAINT
            )
            await session.commit()
        async with SM() as session:
            runs = (
                await session.execute(
                    select(AgentRun).where(
                        AgentRun.complaint_id == SEEDED_COMPLAINT
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    triage = [r for r in runs if r.agent_name == "triage"]
    assert triage
    for run in triage:
        assert run.model_provider is not None, (
            "model_provider must record the provider that served the run"
        )
        assert run.model_provider in {"on_prem", "replay", "mock", "cloud"}


# --- the adapter invents nothing ------------------------------------------


@pytest.mark.asyncio
async def test_validation_record_adapter_invents_no_fields(
    test_database_url, db_schema
):
    """Fields the canonical Tier-1 subset does not carry stay absent.

    ADR 0026 fixes Tier 1 at a 15-field subset with no amount_claimed and
    no currency. Supplying a placeholder for either would put fabricated
    values into a regulator-facing audit row, so the adapter omits them
    and the gap shows up honestly in pass1_failed_rules.
    """
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            record = (
                await session.execute(
                    select(ComplaintRecord).where(
                        ComplaintRecord.complaint_id == SEEDED_COMPLAINT
                    )
                )
            ).scalar_one()
            mapped = canonical_record_to_validation_record(record)
    finally:
        await engine.dispose()

    assert "amount_claimed" not in mapped
    assert "currency" not in mapped
    assert mapped["complaint_id"] == record.complaint_id
    assert mapped["institution_code"] == record.institution_id
    assert mapped["narrative_es"] == record.description_text
