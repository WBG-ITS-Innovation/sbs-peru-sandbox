# SPDX-License-Identifier: Apache-2.0
"""Agent orchestration state machine.

Flow (per ADR 0001):

    complaint-received → run_triage
       └─ if route_to == 'investigation' → run_investigation
           └─ run_synthesis
           └─ (scaffolded) run_cross_source_correlator
       └─ if route_to == 'reject' | 'info-only' → stop

Triggered by the ingestion pipeline after the
``canonical-complaint-persisted`` audit event. Today the trigger is
synchronous (same session) so the demo invariants hold without a
worker dependency; the wrapper is structured so an arq dispatch
slot in below this comment block when a worker is available.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.agents.cross_source_correlator import run_cross_source_correlator
from sbs_api.agents.investigation import run_investigation
from sbs_api.agents.providers import get_provider
from sbs_api.agents.providers.base import ModelProvider
from sbs_api.agents.providers.replay import ReplayFixtureMissing
from sbs_api.agents.synthesis import run_synthesis
from sbs_api.agents.triage import run_triage

log = logging.getLogger(__name__)


@dataclass
class OrchestrationResult:
    triage: dict[str, Any]
    investigation: dict[str, Any] | None
    synthesis: dict[str, Any] | None
    cross_source: dict[str, Any] | None
    route_to: str


async def run_agent_pipeline(
    session: AsyncSession,
    *,
    complaint_id: str,
    provider: ModelProvider | None = None,
    include_scaffolded: bool = True,
) -> OrchestrationResult:
    """Run the full triage → investigation → synthesis chain.

    Returns the structured outputs for each stage so the caller can
    log or assert against them. Each stage writes its own
    ``agent_runs`` row; the caller is expected to ``commit`` once
    after this returns.
    """
    provider = provider or get_provider()

    triage_out = await run_triage(
        session, complaint_id=complaint_id, provider=provider
    )
    route = triage_out.get("route_to") or "info-only"

    investigation_out: dict[str, Any] | None = None
    synthesis_out: dict[str, Any] | None = None
    cross_source_out: dict[str, Any] | None = None

    if route == "investigation":
        investigation_out = await run_investigation(
            session, complaint_id=complaint_id, provider=provider
        )
        synthesis_out = await run_synthesis(
            session, complaint_id=complaint_id, provider=provider
        )
        if include_scaffolded:
            try:
                cross_source_out = await run_cross_source_correlator(
                    session, complaint_id=complaint_id
                )
            except ReplayFixtureMissing:
                # Non-demo complaints do not have a fixture yet — skip
                # the scaffolded agent quietly rather than raising.
                cross_source_out = None
    else:
        log.info(
            "agent pipeline stopping at triage: route_to=%s complaint=%s",
            route,
            complaint_id,
        )

    return OrchestrationResult(
        triage=triage_out,
        investigation=investigation_out,
        synthesis=synthesis_out,
        cross_source=cross_source_out,
        route_to=route,
    )
