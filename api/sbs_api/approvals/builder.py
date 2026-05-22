"""Approvals queue + detail assembly.

The queue endpoint surfaces pending_approvals rows + per-day KPIs.
The detail endpoint reuses the findings detail + adds a "decision
history" summary (empty pre-decision; populated after a decision
lands).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.agent_feedback import AgentFeedback
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.institution import InstitutionRecord
from sbs_api.db.models.pending_approval import PendingApproval
from sbs_api.db.models.supervisory_observation import SupervisoryObservation
from sbs_api.findings.builder import build_finding_detail

# Severity rank for the queue's composite ORDER BY: lower = sorted first.
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


async def build_approvals_queue(
    session: AsyncSession,
    *,
    roles: frozenset[str],
) -> dict[str, Any]:
    """Pending rows (severity-sorted, oldest-first within band) + KPIs."""

    stmt = (
        select(PendingApproval, ComplaintRecord)
        .join(
            ComplaintRecord,
            ComplaintRecord.complaint_id == PendingApproval.complaint_id,
        )
        .where(PendingApproval.status == "pending")
        .order_by(
            # Composite ORDER BY — severity rank ASC, then created_at ASC
            # (oldest-first within the band).
            case(_SEVERITY_RANK, value=PendingApproval.severity, else_=99),
            PendingApproval.created_at.asc(),
        )
        .limit(100)
    )
    rows = (await session.execute(stmt)).all()

    institutions = await _load_institutions(session)

    items: list[dict[str, Any]] = []
    now = datetime.now(tz=timezone.utc)
    for pending, complaint in rows:
        items.append(
            {
                "id": pending.id,
                "complaint_id": pending.complaint_id,
                "institution_id": complaint.institution_id,
                "institution_name": institutions.get(
                    complaint.institution_id, complaint.institution_id
                ),
                "severity": pending.severity,
                "created_at": pending.created_at.isoformat(timespec="seconds"),
                "time_pending_seconds": int(
                    (now - pending.created_at).total_seconds()
                ),
                "created_by": pending.created_by,
            }
        )

    kpis = await _build_kpis(session)
    return {
        "items": items,
        "total_pending": len(items),
        "kpis": kpis,
    }


async def _build_kpis(session: AsyncSession) -> dict[str, Any]:
    now = datetime.now(tz=timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    pending_q = select(func.count()).select_from(PendingApproval).where(
        PendingApproval.status == "pending"
    )
    approved_today_q = (
        select(func.count())
        .select_from(PendingApproval)
        .where(PendingApproval.status == "approved")
        .where(PendingApproval.decided_at >= day_start)
    )
    rejected_today_q = (
        select(func.count())
        .select_from(PendingApproval)
        .where(PendingApproval.status == "rejected")
        .where(PendingApproval.decided_at >= day_start)
    )

    pending_count = (await session.execute(pending_q)).scalar_one()
    approved_today = (await session.execute(approved_today_q)).scalar_one()
    rejected_today = (await session.execute(rejected_today_q)).scalar_one()

    # Median time-to-decision over today's decisions. Postgres has
    # percentile_cont; using SQL avoids pulling rows for compute here.
    median_q = select(
        func.percentile_cont(0.5).within_group(
            func.extract(
                "epoch", PendingApproval.decided_at - PendingApproval.created_at
            )
        )
    ).where(PendingApproval.decided_at >= day_start)
    median_seconds = (await session.execute(median_q)).scalar()

    return {
        "pending": int(pending_count),
        "approved_today": int(approved_today),
        "rejected_today": int(rejected_today),
        "median_time_to_decision_seconds": (
            float(median_seconds) if median_seconds is not None else None
        ),
    }


async def build_approval_detail(
    session: AsyncSession,
    *,
    pending_approval_id: int,
    roles: frozenset[str],
) -> dict[str, Any] | None:
    pending = (
        await session.execute(
            select(PendingApproval).where(PendingApproval.id == pending_approval_id)
        )
    ).scalar_one_or_none()
    if pending is None:
        return None

    finding = await build_finding_detail(
        session, complaint_id=pending.complaint_id, roles=roles
    )
    if finding is None:
        return None

    # Pinned evidence — regex hits + top XGBoost contributions +
    # cross-source channel contributions, surfaced together so the
    # head reads the decision-relevant signals first.
    pinned_evidence = _pinned_evidence(finding)

    # Decision history (post-decision rows for this approval id; empty
    # pre-decision but the shape exists for the audit-revisit case).
    observations = (
        (
            await session.execute(
                select(SupervisoryObservation)
                .where(SupervisoryObservation.pending_approval_id == pending_approval_id)
                .order_by(desc(SupervisoryObservation.approved_at))
            )
        )
        .scalars()
        .all()
    )
    feedback = (
        (
            await session.execute(
                select(AgentFeedback)
                .where(AgentFeedback.pending_approval_id == pending_approval_id)
                .order_by(desc(AgentFeedback.recorded_at))
            )
        )
        .scalars()
        .all()
    )

    return {
        "pending_approval": {
            "id": pending.id,
            "complaint_id": pending.complaint_id,
            "agent_run_id": pending.agent_run_id,
            "status": pending.status,
            "severity": pending.severity,
            "created_by": pending.created_by,
            "created_at": pending.created_at.isoformat(timespec="seconds"),
            "decided_at": pending.decided_at.isoformat(timespec="seconds")
            if pending.decided_at
            else None,
            "decided_by": pending.decided_by,
            "decision_action": pending.decision_action,
            "decision_rationale": pending.decision_rationale,
        },
        "finding": finding,
        "pinned_evidence": pinned_evidence,
        "decision_history": {
            "observations": [
                {
                    "id": o.id,
                    "narrative": o.narrative,
                    "approved_by": o.approved_by,
                    "approved_at": o.approved_at.isoformat(timespec="seconds"),
                }
                for o in observations
            ],
            "feedback": [
                {
                    "id": f.id,
                    "decision": f.decision,
                    "rationale": f.rationale,
                    "edit_diff": f.edit_diff,
                    "recorded_by": f.recorded_by,
                    "recorded_at": f.recorded_at.isoformat(timespec="seconds"),
                }
                for f in feedback
            ],
        },
    }


def _pinned_evidence(finding: dict[str, Any]) -> dict[str, Any]:
    """Pull the three highest-signal pieces from the finding payload."""

    # Regex hits live inside the latest classifier or regex_taxonomy run.
    regex_hits: list[dict[str, Any]] = []
    for run in finding.get("agent_runs", []):
        for tc in run.get("tool_calls", []) or []:
            if tc.get("tool_name") == "regex_taxonomy" and tc.get("output"):
                regex_hits = (tc["output"] or {}).get("matches", [])
                break
        if regex_hits:
            break

    # Top three XGBoost contributions.
    top_features: list[dict[str, Any]] = []
    feats = finding.get("features") or {}
    if feats.get("feature_contributions"):
        ranked = sorted(
            feats["feature_contributions"],
            key=lambda c: abs(c.get("contribution", 0)),
            reverse=True,
        )
        top_features = ranked[:3]

    # Cross-source contributions from the cross-source-correlator run.
    cross_source: list[dict[str, Any]] = []
    for run in finding.get("agent_runs", []):
        if run.get("agent_name") == "cross-source-correlator" and run.get(
            "final_output"
        ):
            cross_source = (run["final_output"] or {}).get(
                "channel_contributions", []
            )
            break

    return {
        "regex_hits": regex_hits,
        "top_features": top_features,
        "cross_source_contributions": cross_source,
    }


async def _load_institutions(session: AsyncSession) -> dict[str, str]:
    rows = (await session.execute(select(InstitutionRecord))).scalars().all()
    return {r.institution_id: r.display_name for r in rows}
