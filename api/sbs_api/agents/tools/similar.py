"""search_similar_complaints — nearest neighbours over recent complaints.

Falls back to exact-match on (product_category, motivo_code,
submotivo) when pgvector is not available. The May 27 demo relies
on the fallback; pgvector is a v0.2 work item.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select

from sbs_api.agents.tools.base import Tool, ToolContext, register_tool
from sbs_api.db.models.complaint import ComplaintRecord


@register_tool
class SearchSimilarComplaintsTool(Tool):
    name = "search_similar_complaints"
    description = (
        "Return up to N recent complaints with the same product/motive "
        "as the input complaint."
    )
    version = "exact-match-v1"
    parameters = {
        "type": "object",
        "properties": {
            "complaint_id": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
        },
    }

    async def run(self, ctx: ToolContext, **kwargs: Any) -> dict[str, Any]:
        complaint_id = kwargs.get("complaint_id") or ctx.complaint_id
        limit = int(kwargs.get("limit", 5))
        if not complaint_id or ctx.session is None:
            return {"items": [], "strategy": "exact-match", "model_id": self.version}

        target = (
            await ctx.session.execute(
                select(ComplaintRecord).where(
                    ComplaintRecord.complaint_id == complaint_id
                )
            )
        ).scalar_one_or_none()
        if target is None:
            return {"items": [], "strategy": "exact-match", "model_id": self.version}

        stmt = (
            select(ComplaintRecord)
            .where(ComplaintRecord.product_category == target.product_category)
            .where(ComplaintRecord.motivo_code == target.motivo_code)
            .where(ComplaintRecord.complaint_id != complaint_id)
            .order_by(desc(ComplaintRecord.received_at))
            .limit(limit)
        )
        rows = (await ctx.session.execute(stmt)).scalars().all()
        items = [
            {
                "complaint_id": r.complaint_id,
                "institution_id": r.institution_id,
                "received_at": r.received_at.isoformat(timespec="seconds"),
                "product_category": r.product_category,
                "motivo_code": r.motivo_code,
                "severity": (r.severity or "MEDIUM").lower(),
            }
            for r in rows
        ]
        return {
            "items": items,
            "strategy": "exact-match",
            "model_id": self.version,
        }
