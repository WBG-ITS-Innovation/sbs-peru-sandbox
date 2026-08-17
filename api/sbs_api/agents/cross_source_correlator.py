# SPDX-License-Identifier: Apache-2.0
"""CrossSourceCorrelatorAgent — correlate across stubbed channels (scaffolded).

Scaffolded: replays a pre-recorded correlation card so the demo
shows the cockpit anomaly tile in sync with the agent's output.
Real INDECOPI / Quantico social / MonitoriA audio ingestion is a
v0.2 work item.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.agents.persistence import finish_agent_run, start_agent_run
from sbs_api.agents.providers.replay import ReplayProvider
from sbs_api.agents.runtime import LoopConfig, run_loop
from sbs_api.agents.tools.base import ToolContext

AGENT_NAME = "cross-source-correlator"
AGENT_VERSION = "cross-source-correlator-0.1.0-scaffold"

SYSTEM_PROMPT = (
    "Eres CrossSourceCorrelatorAgent del prototipo SupTech de la SBS. "
    "Tu rol es correlacionar señales entre reclamos internos, "
    "INDECOPI, redes sociales (Quantico) y monitoreo de audio "
    "(MonitoriA). Llama a compute_anomaly_score y "
    "search_similar_complaints. Las fuentes externas están "
    "stubbed para la fase actual."
)

ALLOWED_TOOLS = ["compute_anomaly_score", "search_similar_complaints"]


async def run_cross_source_correlator(
    session: AsyncSession,
    *,
    complaint_id: str,
    provider: ReplayProvider | None = None,
) -> dict[str, Any]:
    provider = provider or ReplayProvider()
    provider.reset()

    fixture = provider.fixture(AGENT_NAME, complaint_id)
    override = fixture.get("final_output_override") or {}

    run = await start_agent_run(
        session,
        complaint_id=complaint_id,
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
    )

    ctx = ToolContext(
        session=session, complaint_id=complaint_id, agent_name=AGENT_NAME
    )
    try:
        result = await run_loop(
            provider,
            ctx,
            LoopConfig(
                agent_name=AGENT_NAME,
                agent_version=AGENT_VERSION,
                system_prompt=SYSTEM_PROMPT,
                allowed_tools=ALLOWED_TOOLS,
                complaint_id=complaint_id,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        await finish_agent_run(
            session,
            run=run,
            status="failed",
            tool_call_records=[],
            final_output=None,
            error={"code": "CORRELATOR_LOOP_ERROR", "message": str(exc)[:300]},
        )
        raise

    # The cockpit anomaly card reads ``channel_contributions``
    # specifically; map our scaffold output onto that shape.
    signals = override.get("cross_source_signals") or []
    channel_contributions = [
        {"channel": s.get("channel"), "value": s.get("value", 0)}
        for s in signals
    ]

    final_output = {
        "cross_source_signals": signals,
        "correlation_strength": override.get("correlation_strength", 0.0),
        "composite_score": override.get("correlation_strength", 0.0),
        "threshold": 0.70,
        "anomaly_flag": float(override.get("correlation_strength", 0.0)) >= 0.70,
        "channel_contributions": channel_contributions,
        "scaffolded": True,
        "reasoning_summary": result.text or "",
    }

    await finish_agent_run(
        session,
        run=run,
        status="success",
        tool_call_records=result.tool_call_records,
        final_output=final_output,
        model_provider=result.served_by,
        error=None,
    )
    return final_output
