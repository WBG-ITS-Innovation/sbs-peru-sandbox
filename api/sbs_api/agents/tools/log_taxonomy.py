# SPDX-License-Identifier: Apache-2.0
"""log_taxonomy_unknown — record a proposed dictionary entry.

This is the only side-effectful tool in the registry. It writes a
``taxonomy-proposal-logged`` row to the audit chain so the human
reviewer has a trace of every dictionary update the harmonizer
suggested. It does NOT modify the taxonomy dictionary itself —
dictionary updates require human review and go through the standard
ADR-amendment loop.
"""

from __future__ import annotations

from typing import Any

from sbs_api.agents.tools.base import Tool, ToolContext, register_tool
from sbs_api.audit import record_audit_event


@register_tool
class LogTaxonomyUnknownTool(Tool):
    name = "log_taxonomy_unknown"
    description = (
        "Record an audit row proposing a new dictionary entry for an "
        "unknown taxonomy surface form. Human review required before "
        "the dictionary itself is updated."
    )
    version = "v1"
    parameters = {
        "type": "object",
        "required": ["surface_form", "suggested_canonical"],
        "properties": {
            "complaint_id": {"type": "string"},
            "surface_form": {"type": "string", "minLength": 1},
            "suggested_canonical": {"type": "string", "minLength": 1},
            "field_path": {"type": "string"},
        },
    }

    async def run(self, ctx: ToolContext, **kwargs: Any) -> dict[str, Any]:
        complaint_id = kwargs.get("complaint_id") or ctx.complaint_id or "global"
        surface_form = str(kwargs.get("surface_form", "")).strip()
        suggested_canonical = str(kwargs.get("suggested_canonical", "")).strip()
        field_path = str(kwargs.get("field_path", "")).strip()
        if not surface_form or not suggested_canonical:
            return {"recorded": False, "reason": "missing surface_form or suggested_canonical"}

        if ctx.session is None:
            return {"recorded": False, "reason": "no session"}

        await record_audit_event(
            ctx.session,
            actor_type="agent",
            actor_id=ctx.agent_name or "taxonomy-harmonizer",
            action="taxonomy-proposal-logged",
            object_type="taxonomy",
            object_id=complaint_id,
            diff={
                "surface_form": surface_form,
                "suggested_canonical": suggested_canonical,
                "field_path": field_path,
            },
            meta={"requires_human_review": True},
        )
        return {
            "recorded": True,
            "surface_form": surface_form,
            "suggested_canonical": suggested_canonical,
        }
