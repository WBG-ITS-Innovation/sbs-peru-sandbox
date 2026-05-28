"""Sector Broadcast agent (P-RESHAPE-6).

When a FRAUD_EMERGENCE pattern is confirmed HIGH against one FI, SBS
warns the rest of that FI's cohort before they're hit. The attacked FI
(``origin_fi``) is NEVER named in the broadcast — recipients learn the
*shape* of the threat, not who was attacked.

The broadcast is drafted into ``AWAITING_DUAL_APPROVAL``: it never
leaves the system without two distinct approvers (the second a Unit Head
or Superintendent). Narrative is on-prem-only with a deterministic
template fallback, same as Issue Resurface.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.agents.providers import get_provider
from sbs_api.agents.providers.base import ModelProvider
from sbs_api.db.models.institution import InstitutionRecord
from sbs_api.db.models.pattern_detection import PatternDetection
from sbs_api.db.models.sector_broadcast import SectorBroadcast, SectorBroadcastAudit
from sbs_api.peer_risk.cohorts import assign_cohort

log = logging.getLogger(__name__)

AGENT_NAME = "sector-broadcast"
MODEL_ID_TEMPLATE_FALLBACK = "sector-broadcast-template-fallback-v1"

_ALLOWED_PROVIDERS = {"on_prem", "replay", "mock"}
RESPONSE_BUSINESS_DAYS = 5  # tighter than the FIBrief's 15

# Deterministic fraud-indicator → suggested-control map. Controls are a
# FIXED enum (sector_broadcast.SUGGESTED_CONTROLS) — never LLM-generated.
_INDICATOR_TO_CONTROL = {
    "PHISHING_KEYWORD": ["STRENGTHEN_FRAUD_MONITORING", "NOTIFY_CUSTOMERS"],
    "SCAM_KEYWORD": ["STRENGTHEN_FRAUD_MONITORING", "NOTIFY_CUSTOMERS"],
    "FAKE_APP_KEYWORD": ["AUDIT_DIGITAL_ONBOARDING", "NOTIFY_CUSTOMERS"],
    "FAKE_AGENT_KEYWORD": ["AUDIT_DIGITAL_ONBOARDING"],
    "UNAUTHORIZED_FEE_KEYWORD": ["REVIEW_FEE_DISCLOSURE_FLOWS"],
    "UNAUTHORIZED_CHARGE_KEYWORD": ["REVIEW_FEE_DISCLOSURE_FLOWS", "INCREASE_SLA_VIGILANCE"],
}


@dataclass(frozen=True)
class SectorBroadcastDecision:
    drafted: bool
    reason: str
    broadcast_id: str | None = None
    target_fi_codes: tuple[str, ...] = ()


def _controls_for(indicators: list[str]) -> list[str]:
    controls: set[str] = set()
    for ind in indicators:
        controls.update(_INDICATOR_TO_CONTROL.get(ind, []))
    return sorted(controls) or ["STRENGTHEN_FRAUD_MONITORING"]


def _urgency_for(severity_score: float) -> str:
    if severity_score >= 0.85:
        return "CRITICAL"
    if severity_score >= 0.70:
        return "ELEVATED"
    return "ROUTINE"


def _business_days_from(start: datetime, days: int) -> datetime:
    d = start
    added = 0
    while added < days:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def _template_threat_es(indicators: list[str]) -> str:
    inds = ", ".join(indicators) if indicators else "indicadores de fraude"
    return (
        "Se ha detectado una campaña de fraude emergente dirigida a una "
        "entidad de su segmento y tamaño, fusionando señales de redes "
        "sociales, reclamos e INDECOPI. Indicadores observados: "
        f"{inds}. Esta alerta es anónima: no se identifica a la entidad "
        "afectada ni a ninguna entidad par."
    )


def _template_threat_en(indicators: list[str]) -> str:
    inds = ", ".join(indicators) if indicators else "fraud indicators"
    return (
        "An emerging fraud campaign has been detected targeting an "
        "institution in your segment and size, fusing social-media, "
        "complaint, and INDECOPI signals. Observed indicators: "
        f"{inds}. This alert is anonymous: neither the affected institution "
        "nor any peer is identified."
    )


async def _try_llm_threat(
    provider: ModelProvider, *, indicators: list[str], cohort_id: str
) -> tuple[str, str, str] | None:
    prompt = (
        "Genera un JSON con threat_summary_es y threat_summary_en para una "
        "alerta sectorial de fraude. NUNCA nombres a ninguna entidad. "
        f"Indicadores: {indicators}. Cohorte destino: {cohort_id}. Solo JSON."
    )
    try:
        resp = await provider.complete(
            messages=[
                {"role": "system", "content": "Eres el agente Sector Broadcast de la SBS."},
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
        es = parsed.get("threat_summary_es", "")
        en = parsed.get("threat_summary_en", "")
        if es and len(es) > 20:
            joined = f"{es} {en}"
            if "SBS-" in joined:
                log.warning("Sector broadcast LLM leaked an FI id — using template")
                return None
            return es, en, resp.model_id
    except Exception as exc:  # noqa: BLE001
        log.warning("Sector broadcast LLM failed — template fallback: %s", exc)
    return None


async def _cohort_peers(
    session: AsyncSession, *, origin_fi: str
) -> tuple[str, list[str]]:
    """Return (cohort_id, peer_codes) — peers share the origin FI's
    cohort, excluding the origin itself."""
    origin = (
        await session.execute(
            select(InstitutionRecord).where(
                InstitutionRecord.institution_id == origin_fi
            )
        )
    ).scalar_one_or_none()
    if origin is None:
        return ("", [])
    origin_cohort = assign_cohort(
        display_name=origin.display_name,
        tier_classification=origin.tier_classification,
    )
    peers: list[str] = []
    rows = (await session.execute(select(InstitutionRecord))).scalars().all()
    for r in rows:
        if r.institution_id == origin_fi:
            continue
        try:
            c = assign_cohort(
                display_name=r.display_name,
                tier_classification=r.tier_classification,
            )
        except Exception:  # noqa: BLE001
            continue
        if c.cohort_id == origin_cohort.cohort_id:
            peers.append(r.institution_id)
    return (origin_cohort.cohort_id, sorted(peers))


async def evaluate_and_draft_broadcast(
    session: AsyncSession,
    *,
    pattern: PatternDetection,
    provider: ModelProvider | None = None,
    now: datetime | None = None,
) -> SectorBroadcastDecision:
    """Draft a sector broadcast for a HIGH FRAUD_EMERGENCE pattern."""
    now = now or datetime.now(tz=timezone.utc)
    provider = provider or get_provider()

    if provider.name not in _ALLOWED_PROVIDERS:
        raise RuntimeError(
            f"Sector Broadcast requires an on-prem provider in v1; got "
            f"'{provider.name}'."
        )

    if pattern.pattern_type != "FRAUD_EMERGENCE":
        return SectorBroadcastDecision(False, "not_fraud_emergence")
    if pattern.severity_band != "HIGH":
        return SectorBroadcastDecision(False, "not_high")

    # Idempotency: one broadcast per origin pattern.
    existing = (
        await session.execute(
            select(SectorBroadcast).where(
                SectorBroadcast.origin_pattern_id == pattern.pattern_id
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return SectorBroadcastDecision(
            False, "already_drafted", broadcast_id=existing.broadcast_id
        )

    cohort_id, peers = await _cohort_peers(session, origin_fi=pattern.institution_code)
    if not peers:
        return SectorBroadcastDecision(False, "no_peers")

    breakdown = pattern.composite_breakdown or {}
    indicators = list(breakdown.get("threat_indicators") or [])

    llm = await _try_llm_threat(provider, indicators=indicators, cohort_id=cohort_id)
    if llm is not None:
        threat_es, threat_en, model_id = llm
        model_provider = provider.name
    else:
        threat_es = _template_threat_es(indicators)
        threat_en = _template_threat_en(indicators)
        model_id = MODEL_ID_TEMPLATE_FALLBACK
        model_provider = "template"

    broadcast_id = str(uuid.uuid4())
    broadcast = SectorBroadcast(
        broadcast_id=broadcast_id,
        origin_pattern_id=pattern.pattern_id,
        origin_fi_anonymized=True,
        target_fi_codes=peers,
        status="AWAITING_DUAL_APPROVAL",
        threat_summary_es=threat_es,
        threat_summary_en=threat_en,
        threat_indicators=indicators,
        suggested_controls=_controls_for(indicators),
        urgency=_urgency_for(float(pattern.severity_score)),
        response_deadline=_business_days_from(now, RESPONSE_BUSINESS_DAYS),
        requires_dual_approval=True,
        model_id=model_id,
        model_provider=model_provider,
    )
    session.add(broadcast)
    session.add(
        SectorBroadcastAudit(
            broadcast_id=broadcast_id,
            event_type="drafted",
            actor="system",
        )
    )
    await session.flush()
    log.info(
        "sector broadcast drafted broadcast_id=%s cohort=%s peers=%d",
        broadcast_id,
        cohort_id,
        len(peers),
    )
    return SectorBroadcastDecision(
        True, "drafted", broadcast_id=broadcast_id, target_fi_codes=tuple(peers)
    )
