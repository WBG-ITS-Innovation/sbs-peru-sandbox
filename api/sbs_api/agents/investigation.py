"""InvestigationAgent — build the evidence bundle for analyst review.

Triggered from one of **two** sources:

* ``trigger_source = "SYSTEM_SIGNAL"`` — per-complaint path. Triage
  emitted ``system_signal == True`` (outage, fraud-scale, threshold
  breach, or FI-flagged regulatory breach). See P-RESHAPE-1.
* ``trigger_source = "PATTERN"`` — per-pattern path. The aggregation
  job (P-RESHAPE-2) emitted a HIGH-severity ``pattern_detections`` row
  and the orchestrator called :func:`run_investigation_for_pattern`
  against it.

Per-complaint runs follow the original tool-calling loop (rank_features,
compute_anomaly_score, search_similar_complaints, draft_narrative).
Per-pattern runs produce a *structured dossier* — the contributing
evidence is already on the pattern row, so we package it without
re-running the tool loop. Narrative synthesis for pattern-level cases
is intentionally minimal here; that's Peer Risk Radar (P-RESHAPE-3)
territory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.agents.persistence import finish_agent_run, start_agent_run
from sbs_api.agents.providers import get_provider
from sbs_api.agents.providers.base import ModelProvider
from sbs_api.agents.providers.replay import ReplayProvider
from sbs_api.agents.runtime import LoopConfig, run_loop
from sbs_api.agents.tools.base import ToolCallRecord, ToolContext

AGENT_NAME = "investigation"
AGENT_VERSION = "investigation-0.2.0"

TRIGGER_SOURCE_SYSTEM_SIGNAL = "SYSTEM_SIGNAL"
TRIGGER_SOURCE_PATTERN = "PATTERN"


@dataclass(frozen=True)
class PatternContext:
    """Inputs for a pattern-triggered Investigation run.

    The orchestrator builds this from a ``pattern_detections`` row plus
    the contributing complaints + INDECOPI cases it already loaded.
    """

    pattern_id: str
    pattern_type: str
    severity_score: float
    severity_band: str
    institution_id: str
    complaint_category: str
    contributing_complaint_ids: list[str]
    contributing_indecopi_case_ids: list[str] = field(default_factory=list)
    composite_breakdown: dict[str, Any] = field(default_factory=dict)
    fi_profile: dict[str, Any] = field(default_factory=dict)

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
        "trigger_source": TRIGGER_SOURCE_SYSTEM_SIGNAL,
        "pattern_id": None,
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
        error=None
        if status == "success"
        else {
            "code": "TOOL_PARTIAL",
            "message": "one or more tools did not return success",
        },
    )
    return final_output


async def run_investigation_for_pattern(
    session: AsyncSession,
    *,
    pattern: PatternContext,
) -> dict[str, Any]:
    """Pattern-triggered Investigation — produces a structured dossier.

    DEMO_NOTE (P-RESHAPE-2): the cross-source narrative synthesis is
    out of scope here; Peer Risk Radar (P-RESHAPE-3) is the agent that
    will write a paragraph for the supervisor. For now the dossier
    lists evidence — contributing complaint IDs, INDECOPI case IDs,
    composite breakdown, FI profile — without an LLM call. That keeps
    the pattern path deterministic for the demo and the audit chain.
    """
    if not pattern.contributing_complaint_ids:
        raise ValueError(
            "PatternContext must include at least one contributing complaint id"
        )

    anchor_complaint_id = pattern.contributing_complaint_ids[0]
    run = await start_agent_run(
        session,
        complaint_id=anchor_complaint_id,
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
    )

    started = datetime.now(tz=timezone.utc)
    final_output = {
        "trigger_source": TRIGGER_SOURCE_PATTERN,
        "pattern_id": pattern.pattern_id,
        "pattern_type": pattern.pattern_type,
        "severity_score": pattern.severity_score,
        "severity_band": pattern.severity_band,
        "institution_id": pattern.institution_id,
        "complaint_category": pattern.complaint_category,
        "contributing_complaint_ids": list(pattern.contributing_complaint_ids),
        "contributing_indecopi_case_ids": list(
            pattern.contributing_indecopi_case_ids
        ),
        "composite_breakdown": dict(pattern.composite_breakdown),
        "fi_profile": dict(pattern.fi_profile),
        "dossier_format": "evidence-only-v1",
        "reasoning_summary": (
            f"Pattern {pattern.pattern_type} on "
            f"{pattern.institution_id}/{pattern.complaint_category}: "
            f"{len(pattern.contributing_complaint_ids)} complaints, "
            f"{len(pattern.contributing_indecopi_case_ids)} INDECOPI cases. "
            f"Severity {pattern.severity_band} ({pattern.severity_score:.2f})."
        ),
        # The per-complaint output shape stays so cockpit/findings
        # readers do not branch on trigger_source. Anomaly slot carries
        # the composite from the pattern row.
        "anomaly": {
            "composite_score": pattern.severity_score,
            "threshold": 0.70,
            "anomaly_flag": pattern.severity_band == "HIGH",
            "contributions": (pattern.composite_breakdown or {}).get(
                "contributions"
            )
            or {},
            "weights": (pattern.composite_breakdown or {}).get("weights") or {},
            "model_id": "pattern-aggregation-v1",
        },
        "feature_attribution": [],
        "feature_model_id": "pattern-aggregation-v1",
        "similar_complaints": [
            {"complaint_id": cid, "similarity": 1.0}
            for cid in pattern.contributing_complaint_ids[1:]
        ],
        "similar_strategy": "pattern-bucket-membership",
        "draft_narrative": {
            "text": None,
            "length": 0,
            "model_id": "narrative-deferred-to-peer-risk-radar",
        },
        "started_at": started.isoformat(timespec="microseconds"),
    }

    await finish_agent_run(
        session,
        run=run,
        status="success",
        tool_call_records=[],
        final_output=final_output,
        error=None,
    )
    return final_output
