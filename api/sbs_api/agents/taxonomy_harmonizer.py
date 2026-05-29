"""TaxonomyHarmonizerAgent — propose dictionary updates (scaffolded).

Scaffolded: uses the ReplayProvider end-to-end so the demo can
show the multiagentic architecture without requiring a real LLM.
The final_output is read out of the replay fixture's
``final_output_override`` block — this is the explicit "this is a
roadmap agent" signal in the demo.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.agents.persistence import finish_agent_run, start_agent_run
from sbs_api.agents.providers.replay import ReplayProvider
from sbs_api.agents.runtime import LoopConfig, run_loop
from sbs_api.agents.tools.base import ToolContext

AGENT_NAME = "taxonomy-harmonizer"
AGENT_VERSION = "taxonomy-harmonizer-0.1.0-scaffold"

SYSTEM_PROMPT = (
    "Eres TaxonomyHarmonizerAgent del prototipo SupTech de la SBS. "
    "Tu rol es revisar términos desconocidos del diccionario y "
    "proponer entradas canónicas; también detectar señales de "
    "reclasificación de motivos entre periodos. Llama a "
    "query_audit_chain y log_taxonomy_unknown. No actualices el "
    "diccionario directamente: cualquier cambio requiere revisión "
    "humana."
)

ALLOWED_TOOLS = ["query_audit_chain", "log_taxonomy_unknown"]


async def run_taxonomy_harmonizer(
    session: AsyncSession,
    *,
    complaint_id: str,
    provider: ReplayProvider | None = None,
) -> dict[str, Any]:
    """Scaffolded run — always uses ReplayProvider."""
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
            error={"code": "HARMONIZER_LOOP_ERROR", "message": str(exc)[:300]},
        )
        raise

    final_output = {
        "proposed_dictionary_entries": override.get(
            "proposed_dictionary_entries", []
        ),
        "reclassification_signals": override.get(
            "reclassification_signals", []
        ),
        "scaffolded": True,
        "reasoning_summary": result.text or "",
    }

    await finish_agent_run(
        session,
        run=run,
        status="success",
        tool_call_records=result.tool_call_records,
        final_output=final_output,
        error=None,
    )
    return final_output
