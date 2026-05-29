"""TriageAgent — classify, surface DQ + taxonomy issues, route.

The first agent in the chain. Reads the pre-computed DQ report,
taxonomy normalizations, and calls the classifier tool. Decides
``route_to`` ∈ {``investigation``, ``reject``, ``info-only``}.

The classifier output drives the Findings list classification badge
in the supervisor UI; ``route_to`` is the signal the orchestrator
uses to invoke the investigation agent.
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

AGENT_NAME = "triage"
AGENT_VERSION = "triage-0.1.0"

SYSTEM_PROMPT = (
    "Eres TriageAgent del prototipo SupTech de la SBS. Tu objetivo es: "
    "(1) clasificar el reclamo usando classify_complaint, "
    "(2) revisar la calidad de datos vía query_dq_results, "
    "(3) verificar normalizaciones vía query_taxonomy_normalizations, "
    "(4) decidir prioridad y enrutamiento. Devuelve un JSON con las "
    "claves classification, priority, dq_summary, taxonomy_summary, "
    "route_to. No inventes información que los tools no entregaron."
)

ALLOWED_TOOLS = [
    "query_dq_results",
    "query_taxonomy_normalizations",
    "classify_complaint",
]


def _priority_from(classification_confidence: float, dq_errors: int) -> str:
    if classification_confidence >= 0.80 or dq_errors >= 3:
        return "high"
    if classification_confidence >= 0.60:
        return "medium"
    return "low"


def _route_from(priority: str, dq_errors: int) -> str:
    if dq_errors >= 5:
        return "reject"
    if priority == "high":
        return "investigation"
    if priority == "medium":
        return "investigation"
    return "info-only"


def _extract_classification(records: list[ToolCallRecord]) -> dict[str, Any]:
    for r in records:
        if r.tool_name == "classify_complaint" and r.status == "success" and r.output:
            return r.output
    return {"label": "other", "confidence": 0.55, "alternatives": []}


def _extract_dq_summary(records: list[ToolCallRecord]) -> dict[str, int]:
    for r in records:
        if r.tool_name == "query_dq_results" and r.status == "success" and r.output:
            return {
                "errors": len(r.output.get("errors") or []),
                "warnings": len(r.output.get("warnings") or []),
            }
    return {"errors": 0, "warnings": 0}


def _extract_taxonomy_summary(records: list[ToolCallRecord]) -> dict[str, int]:
    for r in records:
        if (
            r.tool_name == "query_taxonomy_normalizations"
            and r.status == "success"
            and r.output
        ):
            return {
                "normalized_count": len(r.output.get("normalizations") or []),
                "unknown_count": len(r.output.get("unknown_terms") or []),
            }
    return {"normalized_count": 0, "unknown_count": 0}


async def run_triage(
    session: AsyncSession,
    *,
    complaint_id: str,
    provider: ModelProvider | None = None,
) -> dict[str, Any]:
    """Run the triage agent against ``complaint_id``.

    Returns the agent's ``final_output`` dict. Side-effect: writes
    one ``agent_runs`` row (status=success|partial|failed) and the
    matching audit-chain rows.
    """
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
            ),
        )
    except Exception as exc:  # noqa: BLE001
        await finish_agent_run(
            session,
            run=run,
            status="failed",
            tool_call_records=[],
            final_output=None,
            error={"code": "TRIAGE_LOOP_ERROR", "message": str(exc)[:300]},
        )
        raise

    classification = _extract_classification(result.tool_call_records)
    dq_summary = _extract_dq_summary(result.tool_call_records)
    taxonomy_summary = _extract_taxonomy_summary(result.tool_call_records)
    priority = _priority_from(
        float(classification.get("confidence", 0.0) or 0.0), dq_summary["errors"]
    )
    route_to = _route_from(priority, dq_summary["errors"])

    final_output = {
        "classification": {
            "label": classification.get("label"),
            "confidence": classification.get("confidence"),
            "alternatives": classification.get("alternatives") or [],
            "model_id": classification.get("model_id"),
        },
        "priority": priority,
        "dq_summary": dq_summary,
        "taxonomy_summary": taxonomy_summary,
        "route_to": route_to,
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
        error=None
        if status == "success"
        else {
            "code": "TOOL_PARTIAL",
            "message": "one or more tools did not return success",
        },
    )
    return final_output
