"""Explanation registry (P-RESHAPE-5).

Every surfaced metric / score / threshold / agent decision in the
cockpit carries an explanation. The UI fetches it from
``GET /v1/internal/explain/{surface_id}`` so explanations stay
versioned with the rule/agent that produced them rather than being
hard-coded (and drifting) in the frontend.

Each entry carries ES (primary) + EN (secondary) text plus provenance:
``source_agent`` | ``source_rule`` | ``source_data_window``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from sbs_api.routes._internal_auth import verify_internal_secret

router = APIRouter(prefix="/internal/explain", tags=["Internal"])


def _e(
    es: str,
    en: str,
    *,
    source_agent: str | None = None,
    source_rule: str | None = None,
    source_data_window: str | None = None,
) -> dict[str, Any]:
    return {
        "es": es,
        "en": en,
        "source_agent": source_agent,
        "source_rule": source_rule,
        "source_data_window": source_data_window,
    }


# The registry. Keyed by surface_id. ≥ 12 entries (acceptance criterion).
EXPLANATIONS: dict[str, dict[str, Any]] = {
    "severity_band": _e(
        "La banda de severidad (ALTA/MEDIA/BAJA) proviene del puntaje "
        "compuesto: ALTA ≥ 0.70, MEDIA ≥ 0.40. Ver el desglose compuesto "
        "para los cinco canales ponderados.",
        "The severity band (HIGH/MEDIUM/LOW) comes from the composite "
        "score: HIGH ≥ 0.70, MEDIUM ≥ 0.40. See the composite breakdown "
        "for the five weighted channels.",
        source_agent="aggregation",
        source_rule="composite_score>=0.70",
    ),
    "severity_score": _e(
        "Puntaje compuesto en [0,1] con pesos fijos: indecopi 0.30, "
        "sentimiento 0.20, narrativa 0.25, velocidad 0.15, mercado 0.10.",
        "Composite score in [0,1] with locked weights: indecopi 0.30, "
        "sentiment 0.20, narrative 0.25, velocity 0.15, market 0.10.",
        source_agent="aggregation",
        source_rule="locked_weights",
    ),
    "percentile": _e(
        "Tu institución supera este porcentaje de pares en su segmento y "
        "tamaño para este motivo de queja. Ventana: últimos 30 días.",
        "Your institution exceeds this percentage of peers in its segment "
        "and size for this complaint reason. Window: last 30 days.",
        source_agent="peer-risk-radar",
        source_data_window="30d",
    ),
    "z_score": _e(
        "Desviaciones estándar respecto a la media de la cohorte. "
        "Outlier si z ≥ 2.0.",
        "Standard deviations from the cohort mean. Outlier if z ≥ 2.0.",
        source_agent="peer-risk-radar",
        source_rule="z_score>=2.0",
        source_data_window="7d",
    ),
    "system_signal": _e(
        "Señal de sistema: marca un reclamo individual como evento de "
        "nivel regulatorio (caída, fraude masivo, umbral de monto, "
        "indicador de incumplimiento). Reglas: OUTAGE_KEYWORD, "
        "FRAUD_KEYWORD, AMOUNT_THRESHOLD, REGULATORY_BREACH_INDICATOR.",
        "System signal: flags an individual complaint as a regulator-level "
        "event (outage, mass fraud, amount threshold, breach indicator). "
        "Rules: OUTAGE_KEYWORD, FRAUD_KEYWORD, AMOUNT_THRESHOLD, "
        "REGULATORY_BREACH_INDICATOR.",
        source_agent="triage",
        source_rule="deterministic_signal_rules_v1",
    ),
    "pattern_type_volume_spike": _e(
        "VOLUME_SPIKE: ≥ 3 reclamos en 24h y ≥ 2.5× el promedio diario "
        "de los 7 días previos (con promedio previo ≥ 1.0).",
        "VOLUME_SPIKE: ≥ 3 complaints in 24h and ≥ 2.5× the prior-7-day "
        "daily mean (prior mean ≥ 1.0).",
        source_agent="aggregation",
        source_rule="VOLUME_SPIKE",
        source_data_window="24h",
    ),
    "pattern_type_cross_source": _e(
        "CROSS_SOURCE_CORRELATION: reclamos suben ≥ 50% semana contra "
        "semana Y casos INDECOPI suben ≥ 30% en la misma ventana.",
        "CROSS_SOURCE_CORRELATION: complaints up ≥ 50% week-over-week AND "
        "INDECOPI cases up ≥ 30% in the same window.",
        source_agent="aggregation",
        source_rule="CROSS_SOURCE_CORRELATION",
        source_data_window="7d",
    ),
    "pattern_type_sustained_elevation": _e(
        "SUSTAINED_ELEVATION: reclamos de 7 días ≥ 1.8× el promedio "
        "semanal de las 4 semanas previas (con promedio previo ≥ 5.0).",
        "SUSTAINED_ELEVATION: 7-day complaints ≥ 1.8× the prior 4-week "
        "weekly mean (prior mean ≥ 5.0).",
        source_agent="aggregation",
        source_rule="SUSTAINED_ELEVATION",
        source_data_window="7d",
    ),
    "pattern_type_new_topic": _e(
        "NEW_TOPIC_EMERGENCE: ≥ 5 reclamos en 24h para una categoría sin "
        "historial en los 30 días previos de esa entidad.",
        "NEW_TOPIC_EMERGENCE: ≥ 5 complaints in 24h for a category with no "
        "history in the institution's prior 30 days.",
        source_agent="aggregation",
        source_rule="NEW_TOPIC_EMERGENCE",
        source_data_window="24h",
    ),
    "forecast_trend_direction": _e(
        "Dirección de tendencia (AL ALZA/ESTABLE/A LA BAJA) proyectada a "
        "14 días con suavizado Holt-Winters sobre la serie diaria.",
        "Trend direction (RISING/STABLE/FALLING) projected 14 days out "
        "with Holt-Winters smoothing over the daily series.",
        source_agent="peer-risk-radar",
        source_rule="holt_winters_alpha0.4_beta0.2",
        source_data_window="30d",
    ),
    "fi_brief_remediation_areas": _e(
        "Áreas de remediación sugeridas (códigos fijos): FEE_DISCLOSURE, "
        "DIGITAL_CHANNEL_RELIABILITY, FRAUD_CONTROLS, COMPLAINT_HANDLING_SLA, "
        "CONTRACT_TRANSPARENCY, OTHER. Mapeadas del motivo, no generadas por IA.",
        "Suggested remediation areas (fixed codes): FEE_DISCLOSURE, "
        "DIGITAL_CHANNEL_RELIABILITY, FRAUD_CONTROLS, COMPLAINT_HANDLING_SLA, "
        "CONTRACT_TRANSPARENCY, OTHER. Mapped from the motivo, not LLM-generated.",
        source_agent="issue-resurface",
        source_rule="motivo_to_remediation_map",
    ),
    "cohort_assignment": _e(
        "La cohorte combina segmento (BANCO/FINANCIERA/CMAC/COOPAC) y "
        "tamaño (TIER_1/2/3). La comparación de pares se hace dentro de la "
        "misma cohorte.",
        "The cohort combines segment (BANCO/FINANCIERA/CMAC/COOPAC) and "
        "size (TIER_1/2/3). Peer comparison happens within the same cohort.",
        source_agent="peer-risk-radar",
        source_rule="segment:size_tier",
    ),
    "fi_brief_approval_consequence": _e(
        "Aprobar este brief lo envía a la entidad por webhook firmado. "
        "Requiere una justificación de ≥ 20 caracteres, registrada en "
        "auditoría. Solo briefs aprobados salen del sistema.",
        "Approving this brief delivers it to the institution over a signed "
        "webhook. Requires a ≥ 20-char rationale, recorded in the audit "
        "log. Only approved briefs leave the system.",
        source_agent=None,
        source_rule="approval_rationale_min_20",
    ),
    "unit_head_override_consequence": _e(
        "Anular la decisión de un Supervisor requiere una justificación de "
        "≥ 50 caracteres (más estricta que la aprobación normal) y queda "
        "registrada en la auditoría de personas.",
        "Overriding a Supervisor decision requires a ≥ 50-char rationale "
        "(stricter than a normal approval) and is recorded in the persona "
        "audit log.",
        source_agent=None,
        source_rule="override_rationale_min_50",
    ),
    "cloud_routing_zero": _e(
        "Inferencia en la nube: 0 llamadas. La política v1 es on-prem "
        "primero (ADR 0001); la nube está bloqueada hasta aprobación legal.",
        "Cloud inference: 0 calls. The v1 policy is on-prem first (ADR "
        "0001); cloud is gated until legal approval.",
        source_agent=None,
        source_rule="on_prem_first_adr_0001",
    ),
}


@router.get(
    "/{surface_id}",
    dependencies=[Depends(verify_internal_secret)],
)
async def explain(surface_id: str) -> dict[str, Any]:
    entry = EXPLANATIONS.get(surface_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown surface_id")
    return {"surface_id": surface_id, **entry}


@router.get(
    "",
    dependencies=[Depends(verify_internal_secret)],
)
async def list_surfaces() -> dict[str, Any]:
    return {"surface_ids": sorted(EXPLANATIONS.keys()), "count": len(EXPLANATIONS)}
