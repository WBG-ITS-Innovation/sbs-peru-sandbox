"""Superintendent (executive) aggregate endpoints (P-RESHAPE-5, Sergio).

Executive view ONLY. No per-complaint rows, no raw narrative — every
handler runs ``assert_no_per_complaint_or_narrative`` before returning.
Requires ``exec:read`` (cohort health, FIBrief activity) or
``peer_risk:read:exec`` (top patterns).

The plain-language pattern summary is an on-prem LLM call with a
deterministic template fallback (same constraint as PRR / Issue
Resurface).
    # DEMO: plain-language summary computed for seeded patterns only.
    # Production rollout requires per-pattern summary validation.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.auth.persona_scopes import EXEC_READ, PEER_RISK_READ_EXEC
from sbs_api.db.models.fi_brief import FIBrief
from sbs_api.db.models.pattern_detection import PatternDetection
from sbs_api.db.models.peer_risk_analysis import PeerRiskAnalysis
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.persona import (
    assert_no_per_complaint_or_narrative,
    requires_scope,
)
from sbs_api.routes._internal_auth import verify_internal_secret

router = APIRouter(prefix="/internal/exec", tags=["Exec"])

_EXEC = requires_scope(EXEC_READ)
_EXEC_PEER = requires_scope(PEER_RISK_READ_EXEC)

_BANNER_ES = (
    "Los datos de reclamos individuales solo son accesibles para los "
    "Analistas de Conducta, tras la anonimización de datos personales, con "
    "trazabilidad de auditoría completa. El Superintendente ve agregados. "
    "SBS TI ve operaciones. La plataforma lo garantiza del lado del servidor."
)

# Cohort health band thresholds (illustrative — count of HIGH patterns
# in the cohort over the window).
def _cohort_band(high_count: int) -> str:
    if high_count == 0:
        return "GREEN"
    if high_count <= 2:
        return "AMBER"
    return "RED"


@router.get(
    "/cohort_health",
    dependencies=[Depends(verify_internal_secret), Depends(_EXEC)],
)
async def cohort_health(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """One band per cohort (GREEN/AMBER/RED) + one-sentence why. The
    cohort is derived per institution; we roll HIGH pattern counts up to
    the cohort level. No per-complaint rows."""
    now = datetime.now(tz=timezone.utc)
    since = now - timedelta(days=7)

    # Map each institution to its cohort.
    from sbs_api.db.models.institution import InstitutionRecord
    from sbs_api.peer_risk.cohorts import assign_cohort

    institutions = (await session.execute(select(InstitutionRecord))).scalars().all()
    inst_to_cohort: dict[str, str] = {}
    for inst in institutions:
        try:
            cohort = assign_cohort(
                display_name=inst.display_name,
                tier_classification=inst.tier_classification,
            )
            inst_to_cohort[inst.institution_id] = cohort.cohort_id
        except Exception:  # noqa: BLE001
            continue

    high_by_cohort: Counter[str] = Counter()
    patterns = (
        await session.execute(
            select(PatternDetection.institution_code, PatternDetection.severity_band)
            .where(PatternDetection.detected_at >= since)
        )
    ).all()
    for inst_code, band in patterns:
        cohort_id = inst_to_cohort.get(inst_code)
        if cohort_id and band == "HIGH":
            high_by_cohort[cohort_id] += 1

    cohorts = sorted(set(inst_to_cohort.values()))
    items = []
    for cohort_id in cohorts:
        high = high_by_cohort.get(cohort_id, 0)
        band = _cohort_band(high)
        why = {
            "GREEN": f"Sin patrones de severidad alta en {cohort_id} esta semana.",
            "AMBER": f"{high} patrón(es) de severidad alta en {cohort_id} esta semana.",
            "RED": f"{high} patrones de severidad alta en {cohort_id}: requiere atención.",
        }[band]
        items.append({"cohort_id": cohort_id, "band": band, "high_pattern_count": high, "why_es": why})

    payload = {"items": items, "banner_es": _BANNER_ES, "generated_at": now.isoformat(timespec="seconds")}
    assert_no_per_complaint_or_narrative(payload)
    return payload


def _template_pattern_summary_es(pattern: PatternDetection) -> str:
    return (
        f"Patrón {pattern.pattern_type} de severidad {pattern.severity_band} "
        f"detectado para la categoría {pattern.complaint_category}. "
        f"Puntaje compuesto {float(pattern.severity_score):.2f}. "
        f"Generado por el motor de agregación determinista."
    )


@router.get(
    "/top_patterns_summary",
    dependencies=[Depends(verify_internal_secret), Depends(_EXEC_PEER)],
)
async def top_patterns_summary(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Top 5 patterns by severity this week, each with a plain-language
    ES summary. NO per-complaint rows; the contributing complaint IDs on
    the pattern row are deliberately omitted from the response."""
    now = datetime.now(tz=timezone.utc)
    since = now - timedelta(days=7)
    rows = (
        await session.execute(
            select(PatternDetection)
            .where(PatternDetection.detected_at >= since)
            .order_by(PatternDetection.severity_score.desc())
            .limit(5)
        )
    ).scalars().all()

    items = []
    for p in rows:
        items.append(
            {
                "pattern_id": p.pattern_id,
                "pattern_type": p.pattern_type,
                "severity_band": p.severity_band,
                "severity_score": float(p.severity_score),
                # Aggregate count only — NOT the contributing complaint IDs.
                "contributing_complaint_count": len(p.contributing_complaint_ids or []),
                "summary_es": _template_pattern_summary_es(p),
            }
        )
    payload = {"items": items, "generated_at": now.isoformat(timespec="seconds")}
    assert_no_per_complaint_or_narrative(payload)
    return payload


@router.get(
    "/fi_brief_activity_aggregate",
    dependencies=[Depends(verify_internal_secret), Depends(_EXEC)],
)
async def fi_brief_activity_aggregate(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Counts only — sent this week, acked, overdue. NO brief contents."""
    now = datetime.now(tz=timezone.utc)
    since = now - timedelta(days=7)
    rows = (await session.execute(select(FIBrief))).scalars().all()

    sent_this_week = sum(
        1 for b in rows if b.sent_at is not None and b.sent_at >= since
    )
    acked = sum(1 for b in rows if b.status == "ACKED")
    overdue = sum(
        1
        for b in rows
        if b.status in {"SENT", "DELIVERED"}
        and b.ack_received_at is None
        and b.response_deadline < now
    )
    by_category: Counter[str] = Counter(b.motivo_code for b in rows)

    payload = {
        "sent_this_week": sent_this_week,
        "acked": acked,
        "overdue": overdue,
        # Category counts are aggregates (how many briefs per reason),
        # not per-complaint rows — allowed at exec level.
        "by_category_count": dict(by_category),
        "generated_at": now.isoformat(timespec="seconds"),
    }
    assert_no_per_complaint_or_narrative(payload)
    return payload


@router.get(
    "/sector_broadcasts",
    dependencies=[Depends(verify_internal_secret), Depends(_EXEC)],
)
async def sector_broadcasts_awaiting(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Top-of-dashboard widget for the Superintendent: sector broadcasts
    awaiting co-approval (the moment Sergio has a clear action). Counts +
    light metadata only — no origin FI, no per-complaint data."""
    from sbs_api.db.models.sector_broadcast import SectorBroadcast

    now = datetime.now(tz=timezone.utc)
    rows = (
        await session.execute(
            select(SectorBroadcast).where(
                SectorBroadcast.status.in_(
                    ["AWAITING_DUAL_APPROVAL", "AWAITING_SECONDARY_APPROVAL"]
                )
            )
        )
    ).scalars().all()

    awaiting_secondary = [
        b for b in rows if b.status == "AWAITING_SECONDARY_APPROVAL"
    ]
    items = [
        {
            "broadcast_id": b.broadcast_id,
            "status": b.status,
            "urgency": b.urgency,
            "target_fi_count": len(b.target_fi_codes),
            "threat_indicators": list(b.threat_indicators),
            "response_deadline": b.response_deadline.isoformat(timespec="seconds"),
        }
        for b in rows
    ]
    payload = {
        "awaiting_co_approval": len(rows),
        "awaiting_my_secondary_approval": len(awaiting_secondary),
        "items": items,
        "generated_at": now.isoformat(timespec="seconds"),
    }
    assert_no_per_complaint_or_narrative(payload)
    return payload
