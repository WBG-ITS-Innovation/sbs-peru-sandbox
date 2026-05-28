"""DIValeVale cockpit monitoring endpoints (P-RESHAPE-8).

The aggregate + per-run views the DIValeVale UI card renders in
P-RESHAPE-10. Persona-scoped:

* Unit Head / Supervisor: all runs, full detail.
* Analyst (Lucía): her assigned FIs only (filtered by ``X-SBS-FI`` —
  the BFF forwards the analyst's assigned institution codes).
* SBS IT (Rosa): telemetry only — counts + latencies, NO
  institution_code, NO per-rule detail.
* Superintendent (Sergio): NOT granted ``agents:read`` → 403 at the
  scope gate. The agent runtime surface is Conduct / IT only.

Requires the ``agents:read`` scope.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.auth.persona_scopes import AGENTS_READ, ROLE_ANALYST, ROLE_SBS_IT
from sbs_api.db.models.validation_audit import ValidationAudit
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.persona import parse_roles_header, requires_scope
from sbs_api.routes._internal_auth import verify_internal_secret

router = APIRouter(prefix="/internal/cockpit/agents/divalevale", tags=["Cockpit"])

_AGENTS = requires_scope(AGENTS_READ)


def _is_it_only(roles: frozenset[str]) -> bool:
    return ROLE_SBS_IT in roles and not (
        roles - {ROLE_SBS_IT}
    )


def _is_analyst_only(roles: frozenset[str]) -> bool:
    return ROLE_ANALYST in roles and not (roles - {ROLE_ANALYST})


def _percentile(latencies: list[int], p: float) -> int | None:
    if not latencies:
        return None
    s = sorted(latencies)
    idx = min(len(s) - 1, int(p * len(s)))
    return s[idx]


@router.get(
    "/activity",
    dependencies=[Depends(verify_internal_secret), Depends(_AGENTS)],
)
async def divalevale_activity(
    window: str = "24h",
    session: AsyncSession = Depends(get_session),
    x_sbs_role: str | None = Header(default=None, alias="X-SBS-Role"),
    x_sbs_fi: str | None = Header(default=None, alias="X-SBS-FI"),
) -> dict[str, Any]:
    roles = parse_roles_header(x_sbs_role)
    now = datetime.now(tz=timezone.utc)
    hours = 24 if window == "24h" else (168 if window == "7d" else 24)
    since = now - timedelta(hours=hours)

    stmt = select(ValidationAudit).where(ValidationAudit.received_at >= since)
    # Analyst sees only her assigned FIs.
    assigned = None
    if _is_analyst_only(roles) and x_sbs_fi:
        assigned = [c.strip() for c in x_sbs_fi.split(",") if c.strip()]
        stmt = stmt.where(ValidationAudit.institution_code.in_(assigned))
    rows = (await session.execute(stmt.order_by(ValidationAudit.received_at.desc()))).scalars().all()

    by_verdict = Counter(r.verdict for r in rows)
    by_routing = Counter(r.routing_action for r in rows)
    latencies = [r.latency_ms for r in rows]
    total = len(rows)
    success = sum(1 for r in rows if r.verdict in ("VALID", "RECOVERABLE"))

    it_only = _is_it_only(roles)
    recent = []
    for r in rows[:20]:
        item: dict[str, Any] = {
            "audit_id": r.audit_id,
            "verdict": r.verdict,
            "routing_action": r.routing_action,
            "tier": r.tier,
            "latency_ms": r.latency_ms,
            "received_at": r.received_at.isoformat(timespec="seconds"),
        }
        if not it_only:
            # Conduct personas see the business context; IT does not.
            item["institution_code"] = r.institution_code
            item["complaint_id"] = r.complaint_id
        recent.append(item)

    return {
        "total_runs": total,
        "by_verdict": dict(by_verdict),
        "by_routing_action": dict(by_routing),
        "recent_runs": recent,
        "success_rate": round(success / total, 3) if total else None,
        "p50_latency_ms": _percentile(latencies, 0.50),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "current_status": "IDLE" if total == 0 else "RUNNING",
        "window": window,
    }


@router.get(
    "/runs/{audit_id}",
    dependencies=[Depends(verify_internal_secret), Depends(_AGENTS)],
)
async def divalevale_run_detail(
    audit_id: str,
    session: AsyncSession = Depends(get_session),
    x_sbs_role: str | None = Header(default=None, alias="X-SBS-Role"),
    x_sbs_fi: str | None = Header(default=None, alias="X-SBS-FI"),
) -> dict[str, Any]:
    roles = parse_roles_header(x_sbs_role)
    row = (
        await session.execute(
            select(ValidationAudit).where(ValidationAudit.audit_id == audit_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # Analyst may only see runs for her assigned FIs.
    if _is_analyst_only(roles) and x_sbs_fi:
        assigned = {c.strip() for c in x_sbs_fi.split(",") if c.strip()}
        if row.institution_code not in assigned:
            raise HTTPException(status_code=404, detail="Run not found")

    if _is_it_only(roles):
        # Telemetry only — no institution, no per-rule detail.
        return {
            "audit_id": row.audit_id,
            "verdict": row.verdict,
            "routing_action": row.routing_action,
            "tier": row.tier,
            "latency_ms": row.latency_ms,
            "received_at": row.received_at.isoformat(timespec="seconds"),
        }

    return {
        "audit_id": row.audit_id,
        "complaint_id": row.complaint_id,
        "institution_code": row.institution_code,
        "verdict": row.verdict,
        "pass1_failed_rules": list(row.pass1_failed_rules),
        "pass2_invoked": row.pass2_invoked,
        "pass2_recoveries": row.pass2_recoveries,
        "pass2_model_id": row.pass2_model_id,
        "routing_action": row.routing_action,
        "batch_id": row.batch_id,
        "tier": row.tier,
        "model_id": row.model_id,
        "model_provider": row.model_provider,
        "latency_ms": row.latency_ms,
        "received_at": row.received_at.isoformat(timespec="seconds"),
    }
