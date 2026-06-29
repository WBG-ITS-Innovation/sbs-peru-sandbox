# SPDX-License-Identifier: Apache-2.0
"""draft_narrative + summarize_for_executive.

The draft tool is the Lucía-facing first cut. For BCO-2026-000001
the draft must OMIT the phrase "comisión por mantenimiento" so the
demo's scripted analyst edit lands on a real gap — that is the
locked demo invariant.

summarize_for_executive collapses the evidence bundle to plain
Spanish for Sergio (Superintendent) or the Supervisor lead.
"""

from __future__ import annotations

from typing import Any

from sbs_api.agents.tools.base import Tool, ToolContext, register_tool

DEMO_COMPLAINT_ID = "BCO-2026-000001"

# Locked demo draft. Notice: no mention of "comisión por mantenimiento" —
# Lucía's edit during the demo fills exactly that gap.
DEMO_DRAFT = (
    "Riesgo de fee disclosure en producto de tarjeta de crédito de la "
    "institución supervisada. La narrativa reporta cargos no informados "
    "al cliente; la calificación BERT clasifica el caso como "
    "'undisclosed-fees-credit' con confianza 0.87. El modelo XGBoost "
    "atribuye el 27% de la decisión a la señal "
    "'narrative_mentions_fee_undisclosed'. El analista debe verificar "
    "el contrato vigente y los rangos de cargo recientes antes de "
    "elevar la observación."
)

DEMO_EXECUTIVE_SUMMARY_SUPERINTENDENT = (
    "Caso BCO-2026-000001: posible cobro de cargos no informados en "
    "tarjeta de crédito. Composite anomaly 0.74 supera el umbral 0.70. "
    "La señal proviene de tres canales: INDECOPI (27%), narrativa "
    "interna (22%) y sentimiento (16%). Se sugiere revisión "
    "supervisora antes de notificar a la institución."
)

DEMO_EXECUTIVE_SUMMARY_SUPERVISOR = (
    "BCO-2026-000001 (BANCO_DEMO_001): cargo no informado en tarjeta "
    "de crédito. Composite 0.74 sobre umbral 0.70; INDECOPI 0.27 / "
    "narrativa 0.22 / sentimiento 0.16. Pendiente confirmar contrato "
    "y rango de cargos antes de elevar a observación."
)


@register_tool
class DraftNarrativeTool(Tool):
    name = "draft_narrative"
    description = (
        "Produce a first-pass narrative for the supervisor's review. "
        "Plain Spanish, factual, no jargon."
    )
    version = "draft-v1"
    parameters = {
        "type": "object",
        "properties": {
            "complaint_id": {"type": "string"},
            "evidence_bundle": {"type": "object"},
        },
    }

    async def run(self, ctx: ToolContext, **kwargs: Any) -> dict[str, Any]:
        complaint_id = kwargs.get("complaint_id") or ctx.complaint_id
        bundle = kwargs.get("evidence_bundle") or {}

        if complaint_id == DEMO_COMPLAINT_ID:
            text = DEMO_DRAFT
        else:
            label = (bundle.get("classification") or {}).get("label") or "—"
            score = (bundle.get("anomaly") or {}).get("composite_score")
            text = (
                f"Reclamo {complaint_id}: clasificación inicial '{label}'. "
                + (
                    f"Composite anomaly {score}. "
                    if score is not None
                    else ""
                )
                + "Pendiente revisión analista."
            )
        return {
            "draft_text": text,
            "length": len(text),
            "model_id": self.version,
        }


@register_tool
class SummarizeForExecutiveTool(Tool):
    name = "summarize_for_executive"
    description = (
        "Collapse the evidence bundle into a plain-Spanish executive "
        "summary. Audience: 'superintendent' (Sergio) or 'supervisor' "
        "(the Supervisor)."
    )
    version = "summarize-v1"
    parameters = {
        "type": "object",
        "properties": {
            "complaint_id": {"type": "string"},
            "audience": {
                "type": "string",
                "enum": ["superintendent", "supervisor"],
            },
        },
    }

    async def run(self, ctx: ToolContext, **kwargs: Any) -> dict[str, Any]:
        complaint_id = kwargs.get("complaint_id") or ctx.complaint_id
        audience = kwargs.get("audience", "superintendent")

        if complaint_id == DEMO_COMPLAINT_ID:
            text = (
                DEMO_EXECUTIVE_SUMMARY_SUPERVISOR
                if audience == "supervisor"
                else DEMO_EXECUTIVE_SUMMARY_SUPERINTENDENT
            )
            key_points = [
                "Composite anomaly 0.74 sobre umbral 0.70.",
                "Señales coincidentes en INDECOPI, narrativa y sentimiento.",
                "Pendiente revisión humana antes de notificación.",
            ]
        else:
            text = (
                f"Reclamo {complaint_id}: pendiente revisión. "
                "No hay señales fuera de umbral en los canales monitoreados."
            )
            key_points = ["Sin señales fuera de umbral."]

        return {
            "summary_text": text,
            "key_points": key_points,
            "audience": audience,
            "model_id": self.version,
        }
