# SPDX-License-Identifier: Apache-2.0
"""SynthesisAgent — plain-Spanish brief for the Superintendent.

Runs after Investigation. Reads the audit chain for context and
calls summarize_for_executive. Output drives the "Executive brief"
sub-panel under Draft summary in the Findings detail view.
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

AGENT_NAME = "synthesis"
AGENT_VERSION = "synthesis-0.1.0"

SYSTEM_PROMPT = (
    "Eres SynthesisAgent del prototipo SupTech de la SBS. Tu rol es "
    "producir un resumen en español plano dirigido al "
    "Superintendente o al jefe de supervisión. Llama a "
    "query_audit_chain y a summarize_for_executive. Evita jerga "
    "técnica; menciona la evidencia clave, no la metodología."
)

ALLOWED_TOOLS = ["query_audit_chain", "summarize_for_executive"]


def _by_tool(records: list[ToolCallRecord], name: str) -> dict[str, Any] | None:
    for r in records:
        if r.tool_name == name and r.status == "success" and r.output:
            return r.output
    return None


async def run_synthesis(
    session: AsyncSession,
    *,
    complaint_id: str,
    audience: str = "superintendent",
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
        session=session,
        complaint_id=complaint_id,
        agent_name=AGENT_NAME,
        extras={"audience": audience},
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
            user_prompt=(
                f"Sintetiza el caso {complaint_id} para una audiencia "
                f"de tipo {audience}."
            ),
        )
    except Exception as exc:  # noqa: BLE001
        await finish_agent_run(
            session,
            run=run,
            status="failed",
            tool_call_records=[],
            final_output=None,
            error={"code": "SYNTHESIS_LOOP_ERROR", "message": str(exc)[:300]},
        )
        raise

    summary = _by_tool(result.tool_call_records, "summarize_for_executive") or {}
    audit = _by_tool(result.tool_call_records, "query_audit_chain") or {}
    events = audit.get("events") or []
    highlights = [
        {
            "action": e.get("action"),
            "actor_id": e.get("actor_id"),
            "created_at": e.get("created_at"),
        }
        for e in events
        if e.get("action")
        in {
            "complaint-received",
            "canonical-complaint-persisted",
            "agent-run-completed",
            "narrative-saved",
            "approval-decided",
        }
    ]

    final_output = {
        "executive_summary": {
            "text": summary.get("summary_text"),
            "key_points": summary.get("key_points") or [],
            "audience": audience,
            "model_id": summary.get("model_id"),
        },
        "audit_trail_highlights": highlights,
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
