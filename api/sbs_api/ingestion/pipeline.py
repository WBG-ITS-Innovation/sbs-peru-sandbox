# SPDX-License-Identifier: Apache-2.0
"""Ingestion pipeline ordering (P-RESHAPE-8).

DIValeVale validation is the FIRST stage — every Tier-1 record passes
through it before Triage. Triage only ever sees VALID or
RECOVERABLE-then-recovered records.

``run_tier1_ingestion`` returns a stage trace so the ordering is
assertable (DIValeVale before Triage). It does NOT replace the existing
demo-ingestion orchestrator; it is the explicit, testable composition of
"validate, then (only if it passes) run the agent pipeline".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.agents.divalevale.agent import ValidationResult, validate_tier1_record
from sbs_api.agents.providers.base import ModelProvider


@dataclass
class PipelineTrace:
    stages: list[str] = field(default_factory=list)
    validation: ValidationResult | None = None
    reached_triage: bool = False


async def run_tier1_ingestion(
    session: AsyncSession,
    *,
    record: dict[str, Any],
    sbs_institution_id: str,
    provider: ModelProvider | None = None,
    now: datetime | None = None,
    sender: Any = None,
    run_triage: bool = False,
) -> PipelineTrace:
    """Validate (DIValeVale) → only on a triage-eligible verdict, hand to
    the agent pipeline. ``run_triage`` is False by default so unit tests
    can assert ordering without standing up the full agent chain; the
    trace records the intended next stage regardless."""
    trace = PipelineTrace()

    # Stage 0 — circuit breaker. SBS IT can PAUSE ingestion for one FI
    # during an incident (P-RESHAPE-9); a paused FI is rejected before any
    # validation work.
    from sbs_api.ingestion.circuit_breaker import assert_ingestion_allowed

    await assert_ingestion_allowed(session, sbs_institution_id)

    # Stage 1 — DIValeVale ALWAYS runs first.
    trace.stages.append("divalevale")
    result = await validate_tier1_record(
        session,
        record=record,
        sbs_institution_id=sbs_institution_id,
        provider=provider,
        now=now,
        sender=sender,
    )
    trace.validation = result

    # Stage 2 — Triage, only for triage-eligible records.
    if result.proceeds_to_triage:
        trace.stages.append("triage")
        trace.reached_triage = True
        if run_triage:
            from sbs_api.agents.orchestrator import run_agent_pipeline

            cid = result.recovered_record.get("complaint_id")
            if cid:
                await run_agent_pipeline(session, complaint_id=cid, provider=provider)
    return trace
