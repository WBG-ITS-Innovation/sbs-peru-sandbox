# SPDX-License-Identifier: Apache-2.0
"""InvestigationAgent — build the evidence bundle for analyst review.

Runs after Triage routes to ``investigation``. Calls
rank_features, compute_anomaly_score, search_similar_complaints,
and draft_narrative. The draft must omit "comisión por
mantenimiento" for BCO-2026-000001 so the demo's scripted edit
lands on a real gap.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.agents.persistence import finish_agent_run, start_agent_run
from sbs_api.agents.providers import get_provider
from sbs_api.agents.providers.base import ModelProvider
from sbs_api.agents.providers.replay import ReplayProvider
from sbs_api.agents.runtime import LoopConfig, run_loop
from sbs_api.agents.tools.base import ToolCallRecord, ToolContext

AGENT_NAME = "investigation"
AGENT_VERSION = "investigation-0.1.0"

SYSTEM_PROMPT = (
    "Eres InvestigationAgent del prototipo SupTech de la SBS. Tu rol "
    "es construir un bundle de evidencia para el analista. Llama a "
    "rank_features, compute_anomaly_score, search_similar_complaints, "
    "y draft_narrative en ese orden. Devuelve únicamente datos que "
    "los tools confirmaron; no inventes cifras."
)

ALLOWED_TOOLS = [
    "rank_features",
    "compute_anomaly_score",
    "search_similar_complaints",
    "draft_narrative",
]


def _by_tool(records: list[ToolCallRecord], name: str) -> dict[str, Any] | None:
    for r in records:
        if r.tool_name == name and r.status == "success" and r.output:
            return r.output
    return None


async def run_investigation(
    session: AsyncSession,
    *,
    complaint_id: str,
    provider: ModelProvider | None = None,
) -> dict[str, Any]:
    provider = provider or get_provider()
    if isinstance(provider, ReplayProvider):
        provider.reset()

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
                max_iterations=6,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        await finish_agent_run(
            session,
            run=run,
            status="failed",
            tool_call_records=[],
            final_output=None,
            error={"code": "INVESTIGATION_LOOP_ERROR", "message": str(exc)[:300]},
        )
        raise

    features = _by_tool(result.tool_call_records, "rank_features") or {}
    anomaly = _by_tool(result.tool_call_records, "compute_anomaly_score") or {}
    similar = _by_tool(result.tool_call_records, "search_similar_complaints") or {}
    draft = _by_tool(result.tool_call_records, "draft_narrative") or {}

    final_output = {
        "feature_attribution": features.get("top_features") or [],
        "feature_model_id": features.get("model_id"),
        "anomaly": {
            "composite_score": anomaly.get("composite_score"),
            "threshold": anomaly.get("threshold"),
            "anomaly_flag": anomaly.get("anomaly_flag"),
            "contributions": anomaly.get("contributions") or {},
            "weights": anomaly.get("weights") or {},
            "model_id": anomaly.get("model_id"),
        },
        "similar_complaints": similar.get("items") or [],
        "similar_strategy": similar.get("strategy"),
        "draft_narrative": {
            "text": draft.get("draft_text"),
            "length": draft.get("length"),
            "model_id": draft.get("model_id"),
        },
        "reasoning_summary": result.text or "",
    }

    status = "partial" if any(
        r.status != "success" for r in result.tool_call_records
    ) else "success"
    await finish_agent_run(
        session,
        run=run,
        status=status,
        tool_call_records=result.tool_call_records,
        final_output=final_output,
        model_provider=result.served_by,
        error=None
        if status == "success"
        else {
            "code": "TOOL_PARTIAL",
            "message": "one or more tools did not return success",
        },
    )
    return final_output
