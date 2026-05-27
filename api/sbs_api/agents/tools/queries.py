"""Read-only query tools — pass-through to existing tables.

These tools never mutate state. They give the agent a structured
view of the work the ingestion pipeline already performed.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from sbs_api.agents.tools.base import Tool, ToolContext, register_tool
from sbs_api.db.models.agent_run import AgentRun
from sbs_api.db.models.audit_event import AuditEvent

INGESTION_AGENT_NAME = "live-ingestion-orchestrator"


@register_tool
class QueryDqResultsTool(Tool):
    name = "query_dq_results"
    description = (
        "Return the data-quality report block from the latest ingestion "
        "agent_run for this complaint."
    )
    version = "v1"
    parameters = {
        "type": "object",
        "properties": {"complaint_id": {"type": "string"}},
    }

    async def run(self, ctx: ToolContext, **kwargs: Any) -> dict[str, Any]:
        complaint_id = kwargs.get("complaint_id") or ctx.complaint_id
        if not complaint_id or ctx.session is None:
            return {"errors": [], "warnings": [], "suggested": []}
        stmt = (
            select(AgentRun)
            .where(AgentRun.complaint_id == complaint_id)
            .where(AgentRun.agent_name == INGESTION_AGENT_NAME)
            .order_by(AgentRun.started_at.desc())
            .limit(1)
        )
        row = (await ctx.session.execute(stmt)).scalar_one_or_none()
        if row is None or not row.final_output:
            return {"errors": [], "warnings": [], "suggested": []}
        dq = row.final_output.get("data_quality") or {}
        annex = row.final_output.get("annex_1a_data_quality") or {}
        return {
            "legacy": dq,
            "annex_1a": annex,
            "errors": (dq.get("errors") or []) + (annex.get("errors") or []),
            "warnings": (dq.get("warnings") or []) + (annex.get("warnings") or []),
            "suggested": dq.get("suggested_enrichments") or [],
        }


@register_tool
class QueryTaxonomyNormalizationsTool(Tool):
    name = "query_taxonomy_normalizations"
    description = (
        "Return the taxonomy normalizations applied during ingestion."
    )
    version = "v1"
    parameters = {
        "type": "object",
        "properties": {"complaint_id": {"type": "string"}},
    }

    async def run(self, ctx: ToolContext, **kwargs: Any) -> dict[str, Any]:
        complaint_id = kwargs.get("complaint_id") or ctx.complaint_id
        if not complaint_id or ctx.session is None:
            return {"normalizations": [], "unknown_terms": []}
        stmt = (
            select(AgentRun)
            .where(AgentRun.complaint_id == complaint_id)
            .where(AgentRun.agent_name == INGESTION_AGENT_NAME)
            .order_by(AgentRun.started_at.desc())
            .limit(1)
        )
        row = (await ctx.session.execute(stmt)).scalar_one_or_none()
        if row is None or not row.final_output:
            return {"normalizations": [], "unknown_terms": []}
        normalizations = row.final_output.get("taxonomy_normalizations") or []
        unknown_terms = [
            n for n in normalizations if n.get("canonical_value") == ""
        ]
        return {
            "normalizations": normalizations,
            "unknown_terms": unknown_terms,
            "flag_unknown_taxonomy": bool(
                row.final_output.get("flag_unknown_taxonomy", False)
            ),
        }


@register_tool
class QueryAuditChainTool(Tool):
    name = "query_audit_chain"
    description = (
        "Return audit events for this complaint in chronological order. "
        "Used by Synthesis to surface what happened, by whom, when."
    )
    version = "v1"
    parameters = {
        "type": "object",
        "properties": {
            "complaint_id": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
        },
    }

    async def run(self, ctx: ToolContext, **kwargs: Any) -> dict[str, Any]:
        complaint_id = kwargs.get("complaint_id") or ctx.complaint_id
        limit = int(kwargs.get("limit", 50))
        if not complaint_id or ctx.session is None:
            return {"events": []}
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.object_id == complaint_id)
            .order_by(AuditEvent.id.asc())
            .limit(limit)
        )
        rows = (await ctx.session.execute(stmt)).scalars().all()
        return {
            "events": [
                {
                    "id": row.id,
                    "actor_type": row.actor_type,
                    "actor_id": row.actor_id,
                    "action": row.action,
                    "created_at": row.created_at.isoformat(timespec="seconds")
                    if row.created_at
                    else None,
                    "meta": row.meta,
                }
                for row in rows
            ]
        }
