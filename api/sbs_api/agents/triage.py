"""TriageAgent — classify, surface DQ + taxonomy issues, flag system signals.

The first agent in the chain. Reads the pre-computed DQ report,
taxonomy normalizations, and calls the classifier tool. Emits a
``system_signal`` boolean (with reason codes) that the orchestrator
uses to decide whether Investigation runs.

``route_to`` is retained as an informational classification of the
complaint (``info-only`` / ``reject``) but **does not** drive
Investigation any more. Per the May-2026 cockpit reshape, Investigation
fires only when ``system_signal`` is True or — separately — when a
pattern-level aggregation crosses a threshold (handled outside this
agent; see P-RESHAPE-2).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.agents.persistence import finish_agent_run, start_agent_run
from sbs_api.agents.providers import get_provider
from sbs_api.agents.providers.base import ModelProvider
from sbs_api.agents.providers.replay import ReplayProvider
from sbs_api.agents.runtime import LoopConfig, run_loop
from sbs_api.agents.tools.base import ToolCallRecord, ToolContext
from sbs_api.agents.triage_signals import SystemSignalResult, detect_system_signal
from sbs_api.db.models.complaint import ComplaintRecord

AGENT_NAME = "triage"
AGENT_VERSION = "triage-0.2.0"

SYSTEM_PROMPT = (
    "Eres TriageAgent del prototipo SupTech de la SBS. Tu objetivo es: "
    "(1) clasificar el reclamo usando classify_complaint, "
    "(2) revisar la calidad de datos vía query_dq_results, "
    "(3) verificar normalizaciones vía query_taxonomy_normalizations, "
    "(4) decidir prioridad y enrutamiento informativo. Devuelve un JSON "
    "con las claves classification, priority, dq_summary, taxonomy_summary, "
    "route_to, system_signal, system_signal_reasons. No inventes "
    "información que los tools no entregaron."
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
    """Informational routing for triage's own reasoning trace.

    ``route_to`` no longer drives Investigation — the orchestrator gates
    on ``system_signal`` instead. The string is kept on ``final_output``
    so the Findings list can still show *why triage thought this row
    mattered* even when Investigation does not run.
    """
    if dq_errors >= 5:
        return "reject"
    if priority in {"high", "medium"}:
        return "review"
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


async def _load_complaint_for_signals(
    session: AsyncSession, complaint_id: str
) -> ComplaintRecord | None:
    return (
        await session.execute(
            select(ComplaintRecord).where(
                ComplaintRecord.complaint_id == complaint_id
            )
        )
    ).scalar_one_or_none()


async def _compute_system_signal(
    session: AsyncSession, complaint_id: str
) -> SystemSignalResult:
    """Run the deterministic detector against the canonical record.

    Returns an empty (flag=False) result when the complaint row is
    missing — the detector itself never raises, so triage's terminal
    status stays the same.
    """
    record = await _load_complaint_for_signals(session, complaint_id)
    if record is None:
        return SystemSignalResult(flag=False, reasons=[])
    return detect_system_signal(
        narrative=record.description_text,
        product_category=record.product_category,
        motivo_code=record.motivo_code,
        # ``ComplaintRecord`` has no amount column today — the orchestrator
        # passes None and the rule simply does not fire. When Annex 1-A
        # adds ``monto_reclamado`` the call site picks it up automatically.
        amount_claimed=None,
        # Same for ``regulatory_breach_indicator``.
        regulatory_breach_indicator=None,
    )


async def run_triage(
    session: AsyncSession,
    *,
    complaint_id: str,
    provider: ModelProvider | None = None,
) -> dict[str, Any]:
    """Run the triage agent against ``complaint_id``.

    Returns the agent's ``final_output`` dict, which carries the new
    ``system_signal`` boolean (and ``system_signal_reasons`` enum codes)
    alongside the existing classification / DQ / taxonomy summaries.
    Side-effect: writes one ``agent_runs`` row (status=success|partial
    |failed) and the matching audit-chain rows.
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
    signal = await _compute_system_signal(session, complaint_id)

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
        "system_signal": signal.flag,
        "system_signal_reasons": signal.reasons,
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
