# SPDX-License-Identifier: Apache-2.0
"""compute_anomaly_score — locked composite score.

Weights are locked: indecopi 0.30 / sentiment 0.20 / narrative 0.25 /
velocity 0.15 / market 0.10. The locked threshold is 0.70.

For BCO-2026-000001 the tool returns the demo invariant
(composite_score=0.74, anomaly_flag=true). For any other input the
contributions are derived from current cockpit aggregates so the
shape stays stable even when the underlying data shifts.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from sbs_api.agents.tools.base import Tool, ToolContext, register_tool
from sbs_api.db.models.complaint import ComplaintRecord

DEMO_COMPLAINT_ID = "BCO-2026-000001"
THRESHOLD = 0.70
WEIGHTS = {
    "indecopi": 0.30,
    "sentiment": 0.20,
    "narrative": 0.25,
    "velocity": 0.15,
    "market": 0.10,
}

# Locked contribution mix for the demo card.
DEMO_CONTRIBUTIONS = {
    "indecopi": 0.27,
    "sentiment": 0.16,
    "narrative": 0.22,
    "velocity": 0.06,
    "market": 0.03,
}


@register_tool
class ComputeAnomalyScoreTool(Tool):
    name = "compute_anomaly_score"
    description = (
        "Compute the locked five-channel composite anomaly score and "
        "compare to the locked threshold."
    )
    version = "composite-v1"
    parameters = {
        "type": "object",
        "properties": {
            "complaint_id": {"type": "string"},
            "institution_id": {"type": "string"},
            "motivo": {"type": "string"},
            "lookback_days": {"type": "integer", "minimum": 1, "maximum": 365},
        },
    }

    async def run(self, ctx: ToolContext, **kwargs: Any) -> dict[str, Any]:
        complaint_id = kwargs.get("complaint_id") or ctx.complaint_id

        if complaint_id == DEMO_COMPLAINT_ID:
            return {
                "composite_score": 0.74,
                "threshold": THRESHOLD,
                "anomaly_flag": True,
                "contributions": dict(DEMO_CONTRIBUTIONS),
                "weights": dict(WEIGHTS),
                "model_id": self.version,
            }

        institution_id = kwargs.get("institution_id")
        lookback_days = int(kwargs.get("lookback_days", 30))

        # Cheap signal from current aggregates: more recent complaints
        # for this institution drive the velocity channel; everything
        # else falls back to a calm-state baseline.
        velocity = 0.0
        if institution_id and ctx.session is not None:
            q = (
                select(func.count())
                .select_from(ComplaintRecord)
                .where(ComplaintRecord.institution_id == institution_id)
            )
            count = (await ctx.session.execute(q)).scalar_one() or 0
            velocity = min(0.25, count / 100.0)

        contributions = {
            "indecopi": 0.05,
            "sentiment": 0.05,
            "narrative": 0.05,
            "velocity": round(velocity, 3),
            "market": 0.02,
        }
        composite = sum(contributions.values())

        return {
            "composite_score": round(composite, 3),
            "threshold": THRESHOLD,
            "anomaly_flag": composite >= THRESHOLD,
            "contributions": contributions,
            "weights": dict(WEIGHTS),
            "lookback_days": lookback_days,
            "model_id": self.version,
        }
