# SPDX-License-Identifier: Apache-2.0
"""classify_complaint — deterministic complaint classifier.

In production this would call BETO via vLLM; today the tool returns
deterministic mappings keyed by (product, motive), reported honestly as
``model_id: rules-v1``. No BETO model is invoked anywhere — the only
``beto-*`` string in this module is the replay id on the locked demo
complaint.

BCO-2026-000001 must classify as undisclosed-fees-credit (0.87) — that is
the locked demo invariant.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from sbs_api.agents.tools.base import Tool, ToolContext, register_tool
from sbs_api.db.models.complaint import ComplaintRecord

DEMO_COMPLAINT_ID = "BCO-2026-000001"

# (product_category, motivo_code) → label, confidence. Keys are compared
# lowercased (see run()).
#
# The canonical block below is keyed on the values the API actually
# accepts — ProductCategory and MotivoCode in sbs_api.models.anexo_1a.
# Until it existed the table held only the prompt-era vocabulary
# ("credit-card", "undisclosed-fee"), which no submission can produce:
# every real complaint missed the table and fell through to
# other @ 0.55, so the classification surfaced in the cockpit carried no
# information at all.
CANONICAL_RULES: dict[tuple[str, str], tuple[str, float]] = {
    ("tarjeta_credito", "cobro_indebido"): ("undisclosed-fees-credit", 0.82),
    ("tarjeta_credito", "operacion_no_reconocida"): ("unauthorized-transaction", 0.79),
    ("tarjeta_debito", "operacion_no_reconocida"): ("unauthorized-transaction", 0.79),
    ("tarjeta_debito", "cobro_indebido"): ("undisclosed-fees-account", 0.76),
    ("depositos", "cobro_indebido"): ("undisclosed-fees-account", 0.78),
    ("depositos", "operacion_no_reconocida"): ("unauthorized-transaction", 0.75),
    ("coopac", "cobro_indebido"): ("undisclosed-fees-account", 0.74),
    ("creditos", "informacion_incorrecta"): ("disputed-rate-loan", 0.74),
    ("creditos", "incumplimiento_contrato"): ("disputed-rate-loan", 0.71),
}

# Prompt-era keys, retained: the Part-12 integration tests and the seeded
# demo rows still carry this vocabulary. Removing them would be a
# behaviour change dressed up as a cleanup.
LEGACY_RULES: dict[tuple[str, str], tuple[str, float]] = {
    ("credit-card", "undisclosed-fee"): ("undisclosed-fees-credit", 0.87),
    ("credit-card", "comisiones"): ("undisclosed-fees-credit", 0.82),
    ("credit-card", "cargo-no-informado"): ("undisclosed-fees-credit", 0.85),
    ("savings-account", "comisiones"): ("undisclosed-fees-account", 0.78),
    ("loan", "tasa-interes"): ("disputed-rate-loan", 0.74),
    ("mobile-app", "fraude"): ("unauthorized-transaction", 0.69),
}

RULES_TABLE: dict[tuple[str, str], tuple[str, float]] = {
    **CANONICAL_RULES,
    **LEGACY_RULES,
}

DEFAULT_LABEL = "other"
DEFAULT_CONFIDENCE = 0.55


@register_tool
class ClassifyComplaintTool(Tool):
    name = "classify_complaint"
    description = (
        "Classify a complaint by (product, motive) into a stable label "
        "and confidence band. Deterministic rules table today; BETO/vLLM "
        "in production."
    )
    version = "rules-v1"
    parameters = {
        "type": "object",
        "properties": {
            "complaint_id": {"type": "string"},
        },
    }

    async def run(self, ctx: ToolContext, **kwargs: Any) -> dict[str, Any]:
        complaint_id = kwargs.get("complaint_id") or ctx.complaint_id
        if not complaint_id:
            raise ValueError("classify_complaint requires complaint_id")

        # Demo invariant: BCO-2026-000001 always classifies as
        # undisclosed-fees-credit (0.87) regardless of session
        # availability. Checked before the optional DB load so the
        # unit-test path (no session) still produces the demo answer.
        if complaint_id == DEMO_COMPLAINT_ID:
            return {
                "label": "undisclosed-fees-credit",
                "confidence": 0.87,
                "alternatives": [
                    {"label": "disputed-rate-loan", "confidence": 0.06},
                    {"label": "other", "confidence": 0.03},
                ],
                "model_id": "beto-replay-v1",
            }

        complaint = await self._load_complaint(ctx, complaint_id)
        if complaint is None:
            return {
                "label": DEFAULT_LABEL,
                "confidence": DEFAULT_CONFIDENCE,
                "alternatives": [],
                "model_id": self.version,
            }

        key = (
            (complaint.product_category or "").lower(),
            (complaint.motivo_code or "").lower(),
        )
        label, conf = RULES_TABLE.get(key, (DEFAULT_LABEL, DEFAULT_CONFIDENCE))
        return {
            "label": label,
            "confidence": conf,
            "alternatives": [],
            "model_id": self.version,
        }

    async def _load_complaint(
        self, ctx: ToolContext, complaint_id: str
    ) -> ComplaintRecord | None:
        if ctx.session is None:
            return None
        result = await ctx.session.execute(
            select(ComplaintRecord).where(
                ComplaintRecord.complaint_id == complaint_id
            )
        )
        return result.scalar_one_or_none()
