"""Peer Risk Radar (PRR) agent — "is this normal?"

The fourth agent in the chain. Invoked downstream of Investigation
when ``trigger_source == PATTERN``. Produces a bilingual narrative
(Spanish primary, English secondary) backed by three deterministic
helpers:

1. **Cohort assignment** — maps the institution to its segment+tier
   comparator pool.
2. **Peer percentiles** — positions the institution's complaint count
   against the cohort distribution (percentile + z-score).
3. **Leading-indicator forecast** — 14-day forward projection via
   hand-rolled Holt-Winters.

The narrative itself is produced by an LLM call to the **on-prem**
provider (Qwen 2.5 14B via vLLM in the WBG ITS tenancy). Cloud is
explicitly blocked for v1. If the LLM output fails schema validation
the agent falls back to a deterministic template narrative built from
the structured fields — the template is labelled with
``model_id="prr-template-fallback-v1"`` so audit can distinguish
it from live LLM output.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.agents.investigation import PatternContext
from sbs_api.agents.persistence import finish_agent_run, start_agent_run
from sbs_api.agents.providers import get_provider
from sbs_api.agents.providers.base import ModelProvider
from sbs_api.db.models.peer_risk_analysis import PeerRiskAnalysis
from sbs_api.peer_risk.cohorts import Cohort, assign_cohort
from sbs_api.peer_risk.forecast import ForecastResult, forecast_series
from sbs_api.peer_risk.percentiles import PercentileResult, compute_peer_percentile

log = logging.getLogger(__name__)

AGENT_NAME = "peer-risk-radar"
AGENT_VERSION = "peer-risk-radar-0.1.0"

MODEL_ID_TEMPLATE_FALLBACK = "prr-template-fallback-v1"

# Providers allowed for narrative generation in v1.
_ALLOWED_PROVIDERS = {"on_prem", "replay", "mock"}

_SYSTEM_PROMPT_ES = (
    "Eres el agente Radar de Riesgo entre Pares de la SBS. Tu tarea es "
    "generar un párrafo narrativo en español que explique la posición de "
    "la entidad dentro de su cohorte de pares. Incluye: (1) el percentil, "
    "(2) si es un outlier, (3) la dirección de la tendencia, "
    "(4) cuántos días ha estado por encima del p90. No inventes cifras; "
    "usa solo los datos proporcionados. Devuelve JSON con las claves "
    "narrative_es y narrative_en."
)

_USER_PROMPT_TEMPLATE = (
    "Datos de análisis:\n"
    "- institution_id: {institution_id}\n"
    "- complaint_category: {motivo_code}\n"
    "- cohort_id: {cohort_id}\n"
    "- peer_count: {peer_count}\n"
    "- percentile: {percentile}\n"
    "- z_score: {z_score}\n"
    "- is_outlier: {is_outlier}\n"
    "- sustained_days_above_p90: {sustained_days}\n"
    "- forecast_trend: {trend_direction}\n"
    "- forecast_strength: {trend_strength}\n"
    "- predicted_next_7d: {predicted_7d}\n"
    "- predicted_next_14d: {predicted_14d}\n"
    "\nGenera un JSON con narrative_es (párrafo en español) y "
    "narrative_en (párrafo en inglés). Solo JSON, sin texto adicional."
)


@dataclass(frozen=True)
class PeerRiskResult:
    analysis_id: str
    cohort_id: str
    peer_count: int
    percentile: float | None
    z_score: float | None
    is_outlier: bool
    sustained_days_above_p90: int
    forecast: dict[str, Any]
    narrative_es: str
    narrative_en: str
    model_id: str
    model_provider: str


def _template_narrative_es(
    percentile: PercentileResult,
    forecast: ForecastResult,
) -> str:
    position = (
        f"percentil {percentile.percentile:.0f}"
        if percentile.percentile is not None
        else "posición no determinada"
    )
    outlier_label = "es un outlier" if percentile.is_outlier else "está dentro del rango normal"
    trend_es = {
        "RISING": "al alza",
        "STABLE": "estable",
        "FALLING": "a la baja",
    }.get(forecast.trend_direction.value, "sin dato")
    return (
        f"La entidad {percentile.institution_id} se ubica en el "
        f"{position} de su cohorte {percentile.cohort_id} "
        f"({percentile.cohort_size} pares) y {outlier_label}. "
        f"Ha estado por encima del p90 durante "
        f"{percentile.sustained_days_above_p90} de los últimos 30 días. "
        f"La tendencia de reclamos para la categoría "
        f"{percentile.motivo_code} es {trend_es} "
        f"(proyección a 7 días: {forecast.predicted_next_7d}, "
        f"a 14 días: {forecast.predicted_next_14d})."
    )


def _template_narrative_en(
    percentile: PercentileResult,
    forecast: ForecastResult,
) -> str:
    position = (
        f"percentile {percentile.percentile:.0f}"
        if percentile.percentile is not None
        else "undetermined position"
    )
    outlier_label = "is an outlier" if percentile.is_outlier else "is within normal range"
    return (
        f"Institution {percentile.institution_id} sits at the "
        f"{position} of its cohort {percentile.cohort_id} "
        f"({percentile.cohort_size} peers) and {outlier_label}. "
        f"It has been above p90 for "
        f"{percentile.sustained_days_above_p90} of the last 30 days. "
        f"The complaint trend for {percentile.motivo_code} is "
        f"{forecast.trend_direction.value.lower()} "
        f"(7-day forecast: {forecast.predicted_next_7d}, "
        f"14-day: {forecast.predicted_next_14d})."
    )


async def _try_llm_narrative(
    provider: ModelProvider,
    *,
    percentile: PercentileResult,
    forecast: ForecastResult,
) -> tuple[str, str, str] | None:
    """Returns (narrative_es, narrative_en, model_id) or None on failure."""
    user_prompt = _USER_PROMPT_TEMPLATE.format(
        institution_id=percentile.institution_id,
        motivo_code=percentile.motivo_code,
        cohort_id=percentile.cohort_id,
        peer_count=percentile.cohort_size,
        percentile=percentile.percentile,
        z_score=percentile.z_score,
        is_outlier=percentile.is_outlier,
        sustained_days=percentile.sustained_days_above_p90,
        trend_direction=forecast.trend_direction.value,
        trend_strength=forecast.trend_strength,
        predicted_7d=forecast.predicted_next_7d,
        predicted_14d=forecast.predicted_next_14d,
    )
    try:
        resp = await provider.complete(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT_ES},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=1024,
            agent_name=AGENT_NAME,
        )
        text = (resp.text or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = json.loads(text)
        nar_es = parsed.get("narrative_es", "")
        nar_en = parsed.get("narrative_en", "")
        if nar_es and len(nar_es) > 20:
            return nar_es, nar_en or "", resp.model_id
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "PRR LLM narrative failed — falling back to template: %s", exc
        )
    return None


async def run_peer_risk_radar(
    session: AsyncSession,
    *,
    pattern: PatternContext,
    provider: ModelProvider | None = None,
    now: datetime | None = None,
) -> PeerRiskResult:
    """Run the Peer Risk Radar agent.

    Produces a ``peer_risk_analyses`` row and returns the structured
    result so the caller (the Investigation orchestrator) can merge it
    into the pattern dossier.
    """
    now = now or datetime.now(tz=timezone.utc)
    provider = provider or get_provider()

    if provider.name not in _ALLOWED_PROVIDERS:
        raise RuntimeError(
            f"Peer Risk Radar requires an on-prem provider in v1; "
            f"got '{provider.name}'. Cloud narrative generation is "
            f"gated on SBS_API_CLOUD_LEGAL_APPROVED and not yet "
            f"implemented for PRR."
        )

    anchor = pattern.contributing_complaint_ids[0]

    run = await start_agent_run(
        session,
        complaint_id=anchor,
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
    )

    # 1. Cohort
    from sbs_api.db.models.institution import InstitutionRecord
    from sqlalchemy import select

    inst = (
        await session.execute(
            select(InstitutionRecord).where(
                InstitutionRecord.institution_id == pattern.institution_id
            )
        )
    ).scalar_one_or_none()
    if inst is None:
        display_name = pattern.institution_id
        tier_class = "small"
    else:
        display_name = inst.display_name
        tier_class = inst.tier_classification

    cohort = assign_cohort(
        display_name=display_name,
        tier_classification=tier_class,
    )

    # 2. Percentiles
    perc = await compute_peer_percentile(
        session,
        institution_id=pattern.institution_id,
        motivo_code=pattern.complaint_category,
        cohort=cohort,
        now=now,
        window_days=7,
    )

    # 3. Forecast
    fc = await forecast_series(
        session,
        institution_id=pattern.institution_id,
        motivo_code=pattern.complaint_category,
        now=now,
        is_demo_seeded=cohort.is_demo_seeded,
    )

    # 4. Narrative
    llm_result = await _try_llm_narrative(
        provider, percentile=perc, forecast=fc
    )
    if llm_result is not None:
        narrative_es, narrative_en, model_id = llm_result
        model_provider = provider.name
    else:
        narrative_es = _template_narrative_es(perc, fc)
        narrative_en = _template_narrative_en(perc, fc)
        model_id = MODEL_ID_TEMPLATE_FALLBACK
        model_provider = "template"

    analysis_id = str(uuid.uuid4())

    forecast_payload = {
        "model_id": fc.model_id,
        "series_observations": fc.series_observations,
        "predicted_next_7d": fc.predicted_next_7d,
        "predicted_next_14d": fc.predicted_next_14d,
        "confidence_interval_low_14d": fc.confidence_interval_low_14d,
        "confidence_interval_high_14d": fc.confidence_interval_high_14d,
        "trend_direction": fc.trend_direction.value,
        "trend_strength": fc.trend_strength,
        "is_pinned_null": fc.is_pinned_null,
    }

    row = PeerRiskAnalysis(
        analysis_id=analysis_id,
        pattern_id=pattern.pattern_id,
        cohort_id=cohort.cohort_id,
        peer_count=perc.cohort_size,
        percentile=perc.percentile,
        z_score=perc.z_score,
        is_outlier=perc.is_outlier,
        forecast=forecast_payload,
        narrative_es=narrative_es,
        narrative_en=narrative_en,
        model_id=model_id,
        model_provider=model_provider,
    )
    session.add(row)

    final_output = {
        "analysis_id": analysis_id,
        "cohort_id": cohort.cohort_id,
        "peer_count": perc.cohort_size,
        "percentile": perc.percentile,
        "z_score": perc.z_score,
        "is_outlier": perc.is_outlier,
        "sustained_days_above_p90": perc.sustained_days_above_p90,
        "forecast": forecast_payload,
        "narrative_es": narrative_es,
        "narrative_en": narrative_en,
        "model_id": model_id,
        "model_provider": model_provider,
    }

    await finish_agent_run(
        session,
        run=run,
        status="success",
        tool_call_records=[],
        final_output=final_output,
        error=None,
    )

    return PeerRiskResult(
        analysis_id=analysis_id,
        cohort_id=cohort.cohort_id,
        peer_count=perc.cohort_size,
        percentile=perc.percentile,
        z_score=perc.z_score,
        is_outlier=perc.is_outlier,
        sustained_days_above_p90=perc.sustained_days_above_p90,
        forecast=forecast_payload,
        narrative_es=narrative_es,
        narrative_en=narrative_en,
        model_id=model_id,
        model_provider=model_provider,
    )
