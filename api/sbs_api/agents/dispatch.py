# SPDX-License-Identifier: Apache-2.0
"""Post-ingestion agent dispatch.

The Part-12 chain (triage → investigation → synthesis) was reachable only
from the demo-ingestion orchestrator, so a complaint submitted through the
canonical Tier-1 route ``POST /v1/complaints`` produced no ``agent_runs``
row at all. This module is the shared entry point both ingestion tiers
call once the canonical row is committed.

Two invariants:

* **Never affects the caller's result.** Tier 1 runs this as a Starlette
  background task, i.e. after the 201 has been written to the wire, and
  every exception is caught and logged here. A failing agent chain must
  not turn a successfully-ingested complaint into an error for the
  institution.
* **Own session, own transaction.** The request-scoped session is closed
  by the time a background task runs, so we open a fresh one from the
  application sessionmaker and commit it ourselves.

Gated on ``SBS_API_AGENTS_PIPELINE_ENABLED`` — the same flag the demo
orchestrator honours — so the default-off posture that keeps the
Prompt-11 regression suite green is unchanged.
"""

from __future__ import annotations

from sbs_api.config import get_settings
from sbs_api.observability.logging import get_logger

_logger = get_logger(__name__)


async def dispatch_agent_pipeline(complaint_id: str, *, tier: str) -> None:
    """Run the agent chain for one freshly-persisted complaint.

    ``tier`` is ``"tier1"`` or ``"tier2"`` and is logged so the two
    ingestion paths are distinguishable in the trace. Never raises.
    """
    settings = get_settings()
    if not settings.agents_pipeline_enabled:
        return

    # Imported lazily: the agent package pulls in the tool registry and the
    # provider clients, which the request path has no reason to load when
    # the pipeline is switched off.
    from sbs_api.agents.ingest_entry import run_agents_for_complaint
    from sbs_api.db.session import get_sessionmaker

    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            outcome = await run_agents_for_complaint(
                session, complaint_id=complaint_id
            )
            await session.commit()
        _logger.info(
            "agents.dispatch.completed",
            complaint_id=complaint_id,
            tier=tier,
            validation_verdict=outcome.validation_verdict,
            route_to=outcome.route_to,
        )
    except Exception as exc:  # noqa: BLE001 — best effort by contract
        _logger.error(
            "agents.dispatch.failed",
            complaint_id=complaint_id,
            tier=tier,
            error_type=type(exc).__name__,
            error=str(exc)[:200],
        )
