"""Issue Resurface agent — close the loop with the FI.

When Peer Risk Radar flags an institution as a sustained HIGH-severity
outlier, this agent drafts a pre-escalation feedback brief addressed to
the FI's conduct officer. The brief never leaves the system without
supervisor approval (it enters ``AWAITING_APPROVAL``).

Trigger conditions — ALL must hold:

* ``PeerRiskAnalysis.is_outlier`` is True
* ``PeerRiskAnalysis.percentile`` >= 90
* linked ``PatternDetection.severity_band`` == 'HIGH'
* ``sustained_days_above_p90`` >= 7 (sustained, not a one-day spike)
* no FIBrief for the same (institution_id, motivo_code) with a
  live status in the last 30 days (the cooldown)

Narrative is on-prem-only (cloud rejected in v1, same as PRR). The
peer-context text is **peer-anonymous** — it states the institution's
own position ("percentil 94 entre bancos de tu segmento y tamaño")
and never names a peer. ``suggested_remediation_areas`` are fixed enum
codes mapped deterministically from the complaint motivo — never
LLM-generated.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.agents.peer_risk_radar import PeerRiskResult
from sbs_api.agents.providers import get_provider
from sbs_api.agents.providers.base import ModelProvider
from sbs_api.db.models.fi_brief import FIBrief
from sbs_api.db.models.fi_brief_audit import FIBriefAudit
from sbs_api.db.models.pattern_detection import PatternDetection

log = logging.getLogger(__name__)

AGENT_NAME = "issue-resurface"
MODEL_ID_TEMPLATE_FALLBACK = "issue-resurface-template-fallback-v1"

_ALLOWED_PROVIDERS = {"on_prem", "replay", "mock"}

# Cooldown + deadline windows.
COOLDOWN_DAYS = 30
DEFAULT_RESPONSE_BUSINESS_DAYS = 15
# Statuses that count as a "live" brief for cooldown purposes — a brief
# that was rejected does NOT block a fresh one.
_COOLDOWN_LIVE_STATUSES = ("APPROVED", "PENDING", "SENT", "DELIVERED", "ACKED")

SUSTAINED_DAYS_THRESHOLD = 7
PERCENTILE_THRESHOLD = 90.0

# Deterministic motivo → remediation-area mapping. The codes are a
# FIXED enum (see fi_brief.REMEDIATION_AREAS) — never produced by the LLM.
_MOTIVO_TO_REMEDIATION = {
    "COBRO_INDEBIDO": ["FEE_DISCLOSURE", "CONTRACT_TRANSPARENCY"],
    "OPERACION_NO_RECONOCIDA": ["FRAUD_CONTROLS"],
    "DEMORA_ATENCION": ["COMPLAINT_HANDLING_SLA"],
    "CALIDAD_SERVICIO": ["DIGITAL_CHANNEL_RELIABILITY", "COMPLAINT_HANDLING_SLA"],
    "INCUMPLIMIENTO_CONTRATO": ["CONTRACT_TRANSPARENCY"],
    "INFORMACION_INCORRECTA": ["CONTRACT_TRANSPARENCY"],
    "PUBLICIDAD_ENGANOSA": ["CONTRACT_TRANSPARENCY"],
}


@dataclass(frozen=True)
class ResurfaceDecision:
    """Outcome of evaluating the trigger. ``brief_id`` is set only when
    a brief was actually drafted."""

    drafted: bool
    reason: str
    brief_id: str | None = None


def _remediation_areas_for(motivo_code: str) -> list[str]:
    return _MOTIVO_TO_REMEDIATION.get(motivo_code, ["OTHER"])


def _business_days_from(start: datetime, days: int) -> datetime:
    """Add ``days`` business days (Mon–Fri) to ``start``."""
    d = start
    added = 0
    while added < days:
        d = d + timedelta(days=1)
        if d.weekday() < 5:  # 0–4 = Mon–Fri
            added += 1
    return d


def _template_pattern_summary_es(
    *, institution_id: str, motivo_code: str, complaint_count: int
) -> str:
    return (
        f"Se ha detectado un patrón sostenido de reclamos en la categoría "
        f"{motivo_code} para su institución ({institution_id}): "
        f"{complaint_count} reclamos en la ventana evaluada, con severidad "
        f"alta y posición de outlier respecto a su cohorte de pares."
    )


def _template_pattern_summary_en(
    *, institution_id: str, motivo_code: str, complaint_count: int
) -> str:
    return (
        f"A sustained complaint pattern has been detected in category "
        f"{motivo_code} for your institution ({institution_id}): "
        f"{complaint_count} complaints in the evaluated window, with high "
        f"severity and an outlier position relative to your peer cohort."
    )


def _template_peer_context_es(*, percentile: float | None, cohort_id: str) -> str:
    pct = f"{percentile:.0f}" if percentile is not None else "—"
    segment = cohort_id.split(":", 1)[0].lower()
    return (
        f"Su institución se ubica en el percentil {pct} entre entidades de "
        f"tipo {segment} de su mismo segmento y tamaño. Esta comparación es "
        f"anónima: no se identifica a ninguna entidad par."
    )


def _template_peer_context_en(*, percentile: float | None, cohort_id: str) -> str:
    pct = f"{percentile:.0f}" if percentile is not None else "—"
    segment = cohort_id.split(":", 1)[0].lower()
    return (
        f"Your institution sits at percentile {pct} among {segment} entities "
        f"of the same segment and size. This comparison is anonymous: no peer "
        f"institution is identified."
    )


async def _cooldown_active(
    session: AsyncSession, *, institution_id: str, motivo_code: str, now: datetime
) -> bool:
    cutoff = now - timedelta(days=COOLDOWN_DAYS)
    existing = (
        await session.execute(
            select(FIBrief.brief_id).where(
                FIBrief.institution_id == institution_id,
                FIBrief.motivo_code == motivo_code,
                FIBrief.status.in_(_COOLDOWN_LIVE_STATUSES),
                FIBrief.created_at >= cutoff,
            )
        )
    ).first()
    return existing is not None


async def _try_llm_narrative(
    provider: ModelProvider,
    *,
    institution_id: str,
    motivo_code: str,
    percentile: float | None,
    cohort_id: str,
    complaint_count: int,
) -> dict[str, str] | None:
    """Returns dict with the four narrative fields + model_id, or None."""
    prompt = (
        "Genera un JSON con las claves pattern_summary_es, pattern_summary_en, "
        "peer_context_es, peer_context_en para un brief de retroalimentación "
        "a una entidad financiera. NUNCA nombres a una entidad par; usa solo "
        "el percentil. Datos:\n"
        f"- institution_id: {institution_id}\n"
        f"- motivo: {motivo_code}\n"
        f"- percentil: {percentile}\n"
        f"- cohorte: {cohort_id}\n"
        f"- reclamos: {complaint_count}\n"
        "Solo JSON."
    )
    try:
        resp = await provider.complete(
            messages=[
                {"role": "system", "content": "Eres el agente Issue Resurface de la SBS."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=1024,
            agent_name=AGENT_NAME,
        )
        text = (resp.text or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = json.loads(text)
        required = (
            "pattern_summary_es",
            "peer_context_es",
        )
        if all(parsed.get(k) and len(parsed[k]) > 20 for k in required):
            # Peer-anonymity guard: reject LLM output that smuggled an
            # institution_id-shaped token into any narrative field.
            joined = " ".join(str(v) for v in parsed.values())
            if "SBS-" in joined:
                log.warning("Issue Resurface LLM leaked an FI id — using template")
                return None
            return {
                "pattern_summary_es": parsed["pattern_summary_es"],
                "pattern_summary_en": parsed.get("pattern_summary_en", ""),
                "peer_context_es": parsed["peer_context_es"],
                "peer_context_en": parsed.get("peer_context_en", ""),
                "model_id": resp.model_id,
            }
    except Exception as exc:  # noqa: BLE001
        log.warning("Issue Resurface LLM failed — template fallback: %s", exc)
    return None


async def evaluate_and_draft(
    session: AsyncSession,
    *,
    pattern: PatternDetection,
    peer_risk: PeerRiskResult,
    provider: ModelProvider | None = None,
    now: datetime | None = None,
) -> ResurfaceDecision:
    """Evaluate the trigger conditions and, if all hold, draft an
    FIBrief in ``AWAITING_APPROVAL``. Returns a :class:`ResurfaceDecision`
    explaining the outcome either way."""
    now = now or datetime.now(tz=timezone.utc)
    provider = provider or get_provider()

    if provider.name not in _ALLOWED_PROVIDERS:
        raise RuntimeError(
            f"Issue Resurface requires an on-prem provider in v1; got "
            f"'{provider.name}'. Cloud narrative generation is gated."
        )

    # --- Trigger conditions -------------------------------------------------
    if not peer_risk.is_outlier:
        return ResurfaceDecision(False, "not_outlier")
    if peer_risk.percentile is None or peer_risk.percentile < PERCENTILE_THRESHOLD:
        return ResurfaceDecision(False, "below_percentile_threshold")
    if pattern.severity_band != "HIGH":
        return ResurfaceDecision(False, "pattern_not_high")
    if peer_risk.sustained_days_above_p90 < SUSTAINED_DAYS_THRESHOLD:
        return ResurfaceDecision(False, "not_sustained")

    if await _cooldown_active(
        session,
        institution_id=pattern.institution_code,
        motivo_code=pattern.complaint_category,
        now=now,
    ):
        return ResurfaceDecision(False, "cooldown_active")

    # --- Narrative ----------------------------------------------------------
    complaint_count = len(pattern.contributing_complaint_ids or [])
    llm = await _try_llm_narrative(
        provider,
        institution_id=pattern.institution_code,
        motivo_code=pattern.complaint_category,
        percentile=peer_risk.percentile,
        cohort_id=peer_risk.cohort_id,
        complaint_count=complaint_count,
    )
    if llm is not None:
        pattern_summary_es = llm["pattern_summary_es"]
        pattern_summary_en = llm["pattern_summary_en"]
        peer_context_es = llm["peer_context_es"]
        peer_context_en = llm["peer_context_en"]
        model_id = llm["model_id"]
        model_provider = provider.name
    else:
        pattern_summary_es = _template_pattern_summary_es(
            institution_id=pattern.institution_code,
            motivo_code=pattern.complaint_category,
            complaint_count=complaint_count,
        )
        pattern_summary_en = _template_pattern_summary_en(
            institution_id=pattern.institution_code,
            motivo_code=pattern.complaint_category,
            complaint_count=complaint_count,
        )
        peer_context_es = _template_peer_context_es(
            percentile=peer_risk.percentile, cohort_id=peer_risk.cohort_id
        )
        peer_context_en = _template_peer_context_en(
            percentile=peer_risk.percentile, cohort_id=peer_risk.cohort_id
        )
        model_id = MODEL_ID_TEMPLATE_FALLBACK
        model_provider = "template"

    # --- Persist DRAFT → AWAITING_APPROVAL ---------------------------------
    brief_id = str(uuid.uuid4())
    deadline = _business_days_from(now, DEFAULT_RESPONSE_BUSINESS_DAYS)
    brief = FIBrief(
        brief_id=brief_id,
        peer_risk_analysis_id=peer_risk.analysis_id,
        pattern_id=pattern.pattern_id,
        institution_id=pattern.institution_code,
        motivo_code=pattern.complaint_category,
        status="AWAITING_APPROVAL",
        pattern_summary_es=pattern_summary_es,
        pattern_summary_en=pattern_summary_en,
        peer_context_es=peer_context_es,
        peer_context_en=peer_context_en,
        suggested_remediation_areas=_remediation_areas_for(
            pattern.complaint_category
        ),
        response_deadline=deadline,
        evidence_complaint_count=complaint_count,
        evidence_window_start=pattern.window_start,
        evidence_window_end=pattern.window_end,
        model_id=model_id,
        model_provider=model_provider,
    )
    session.add(brief)
    session.add(
        FIBriefAudit(
            brief_id=brief_id,
            event_type="drafted",
            event_payload={
                "trigger": "peer_risk_outlier",
                "percentile": peer_risk.percentile,
                "sustained_days_above_p90": peer_risk.sustained_days_above_p90,
                "model_provider": model_provider,
            },
            actor="system",
        )
    )
    await session.flush()
    log.info(
        "Issue Resurface drafted brief_id=%s institution=%s motivo=%s",
        brief_id,
        pattern.institution_code,
        pattern.complaint_category,
    )
    return ResurfaceDecision(True, "drafted", brief_id=brief_id)
