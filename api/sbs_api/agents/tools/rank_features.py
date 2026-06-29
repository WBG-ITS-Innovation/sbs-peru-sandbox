# SPDX-License-Identifier: Apache-2.0
"""rank_features — top-N SHAP-shaped feature attribution.

Deterministic per (complaint_id). BCO-2026-000001 returns the
locked demo invariant set with narrative_mentions_fee_undisclosed at
the top (+0.27).
"""

from __future__ import annotations

from typing import Any

from sbs_api.agents.tools.base import Tool, ToolContext, register_tool

DEMO_COMPLAINT_ID = "BCO-2026-000001"

DEMO_FEATURES = [
    {"name": "narrative_mentions_fee_undisclosed", "contribution": 0.27},
    {"name": "product_category=credit-card", "contribution": 0.18},
    {"name": "indecopi_history_180d", "contribution": 0.14},
    {"name": "amount_claimed_band=mid", "contribution": 0.09},
    {"name": "complainant_district=lima", "contribution": 0.04},
]

DEFAULT_FEATURES = [
    {"name": "product_category", "contribution": 0.12},
    {"name": "motivo_code", "contribution": 0.09},
    {"name": "amount_band", "contribution": 0.06},
]


@register_tool
class RankFeaturesTool(Tool):
    name = "rank_features"
    description = (
        "Return top-N feature contributions (SHAP-shaped) for the "
        "complaint's classification. Deterministic XGBoost replay for "
        "the May 27 demo."
    )
    version = "xgboost-replay-v1"
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

        if complaint_id == DEMO_COMPLAINT_ID:
            features = DEMO_FEATURES[:limit]
        else:
            features = DEFAULT_FEATURES[:limit]

        return {
            "top_features": features,
            "model_id": self.version,
        }
