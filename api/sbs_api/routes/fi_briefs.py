"""FIBrief approval queue + decision endpoints + FI ack ingestion.

The approval flow mirrors the existing findings-approval pattern
(``routes/approvals.py``): server-enforced 20-char rationale, head-only
role gate, append-only audit. Only an APPROVED brief is ever delivered.

Decisions:
* approve          → status APPROVED, then deliver via the outbound
                     webhook channel (status walks to DELIVERED).
* reject           → status REJECTED (rationale >= 20 chars).
* edit-and-approve → narrative text replaced + re-validated for
                     peer-anonymity, then APPROVED + delivered.

Ack ingestion (``POST /v1/internal/fi_brief/{brief_id}/ack``) captures
the FI's acknowledgement. DEMO: ack capture only — the downstream
consumer (Compliance Tracker) is a v2 agent, deferred.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.fi_brief import FIBrief
from sbs_api.db.models.fi_brief_audit import FIBriefAudit
from sbs_api.dependencies.db import get_session
from sbs_api.routes._internal_auth import (
    require_any_role,
    verify_internal_secret,
)
from sbs_api.webhooks.fi_brief_delivery import deliver_fi_brief

router = APIRouter(prefix="/internal", tags=["Internal"])

_HEAD_ONLY = require_any_role({"sbs:conduct:head"})


# A peer-anonymity guard reused by edit-and-approve: edited narrative
# must not smuggle an FI id token in.
def _assert_peer_anonymous(*texts: str | None) -> None:
    for t in texts:
        if t and "SBS-" in t:
            raise HTTPException(
                status_code=422,
                detail="narrative must be peer-anonymous (no institution ids)",
            )


async def _load_brief(session: AsyncSession, brief_id: str) -> FIBrief:
    brief = (
        await session.execute(
            select(FIBrief).where(FIBrief.brief_id == brief_id)
        )
    ).scalar_one_or_none()
    if brief is None:
        raise HTTPException(status_code=404, detail="FIBrief not found")
    return brief


# --- GET /v1/internal/fi_briefs (queue) -----------------------------------


@router.get(
    "/fi_briefs",
    dependencies=[Depends(verify_internal_secret), Depends(_HEAD_ONLY)],
)
async def list_fi_briefs(
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(FIBrief).order_by(FIBrief.created_at.desc()).limit(100)
    if status:
        stmt = stmt.where(FIBrief.status == status)
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "items": [
            {
                "brief_id": b.brief_id,
                "institution_id": b.institution_id,
                "motivo_code": b.motivo_code,
                "status": b.status,
                "created_at": b.created_at.isoformat(timespec="seconds"),
                "response_deadline": b.response_deadline.isoformat(
                    timespec="seconds"
                ),
            }
            for b in rows
        ],
        "total": len(rows),
    }


# --- POST /v1/internal/fi_briefs/{id}/approve -----------------------------


class ApproveBriefRequest(BaseModel):
    actor_id: str = Field(min_length=1, max_length=128)
    rationale: str = Field(
        min_length=20,
        max_length=2_000,
        description="Why the brief is approved — >= 20 chars (server-enforced).",
    )


class EditApproveBriefRequest(ApproveBriefRequest):
    edited_pattern_summary_es: str = Field(min_length=1, max_length=10_000)
    edited_peer_context_es: str = Field(min_length=1, max_length=10_000)


class RejectBriefRequest(BaseModel):
    actor_id: str = Field(min_length=1, max_length=128)
    rationale: str = Field(min_length=20, max_length=2_000)


class _BriefDecisionResponse(BaseModel):
    brief_id: str
    status: str
    delivery_attempts: int


async def _approve_and_deliver(
    session: AsyncSession, brief: FIBrief, *, actor_id: str, rationale: str
) -> _BriefDecisionResponse:
    now = datetime.now(tz=timezone.utc)
    brief.status = "APPROVED"
    brief.approved_by = actor_id
    brief.approved_at = now
    brief.approval_rationale = rationale
    session.add(
        FIBriefAudit(
            brief_id=brief.brief_id,
            event_type="approved",
            event_payload={"rationale_excerpt": rationale[:200]},
            actor=actor_id,
        )
    )
    await session.flush()

    outcome = await deliver_fi_brief(session, brief_id=brief.brief_id)
    await session.commit()
    return _BriefDecisionResponse(
        brief_id=brief.brief_id,
        status=outcome.status,
        delivery_attempts=outcome.attempts,
    )


@router.post(
    "/fi_briefs/{brief_id}/approve",
    response_model=_BriefDecisionResponse,
    status_code=201,
    dependencies=[Depends(verify_internal_secret), Depends(_HEAD_ONLY)],
)
async def approve_brief(
    brief_id: str,
    body: ApproveBriefRequest,
    session: AsyncSession = Depends(get_session),
) -> _BriefDecisionResponse:
    brief = await _load_brief(session, brief_id)
    if brief.status != "AWAITING_APPROVAL":
        raise HTTPException(
            status_code=409,
            detail=f"brief is {brief.status}, cannot approve",
        )
    return await _approve_and_deliver(
        session, brief, actor_id=body.actor_id, rationale=body.rationale
    )


@router.post(
    "/fi_briefs/{brief_id}/edit-and-approve",
    response_model=_BriefDecisionResponse,
    status_code=201,
    dependencies=[Depends(verify_internal_secret), Depends(_HEAD_ONLY)],
)
async def edit_and_approve_brief(
    brief_id: str,
    body: EditApproveBriefRequest,
    session: AsyncSession = Depends(get_session),
) -> _BriefDecisionResponse:
    brief = await _load_brief(session, brief_id)
    if brief.status != "AWAITING_APPROVAL":
        raise HTTPException(
            status_code=409,
            detail=f"brief is {brief.status}, cannot edit-and-approve",
        )
    _assert_peer_anonymous(
        body.edited_pattern_summary_es, body.edited_peer_context_es
    )
    brief.pattern_summary_es = body.edited_pattern_summary_es
    brief.peer_context_es = body.edited_peer_context_es
    session.add(
        FIBriefAudit(
            brief_id=brief.brief_id,
            event_type="edited",
            event_payload={"actor": body.actor_id},
            actor=body.actor_id,
        )
    )
    await session.flush()
    return await _approve_and_deliver(
        session, brief, actor_id=body.actor_id, rationale=body.rationale
    )


@router.post(
    "/fi_briefs/{brief_id}/reject",
    response_model=_BriefDecisionResponse,
    status_code=201,
    dependencies=[Depends(verify_internal_secret), Depends(_HEAD_ONLY)],
)
async def reject_brief(
    brief_id: str,
    body: RejectBriefRequest,
    session: AsyncSession = Depends(get_session),
) -> _BriefDecisionResponse:
    brief = await _load_brief(session, brief_id)
    if brief.status != "AWAITING_APPROVAL":
        raise HTTPException(
            status_code=409,
            detail=f"brief is {brief.status}, cannot reject",
        )
    now = datetime.now(tz=timezone.utc)
    brief.status = "REJECTED"
    brief.rejected_by = body.actor_id
    brief.rejected_at = now
    brief.rejection_reason = body.rationale
    session.add(
        FIBriefAudit(
            brief_id=brief.brief_id,
            event_type="rejected",
            event_payload={"rationale_excerpt": body.rationale[:200]},
            actor=body.actor_id,
        )
    )
    await session.flush()
    await session.commit()
    return _BriefDecisionResponse(
        brief_id=brief.brief_id, status="REJECTED", delivery_attempts=0
    )


# --- POST /v1/internal/fi_brief/{id}/ack ----------------------------------


class AckRequest(BaseModel):
    response_codes: list[str] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=4_000)


@router.post(
    "/fi_brief/{brief_id}/ack",
    status_code=202,
    dependencies=[Depends(verify_internal_secret)],
)
async def ack_fi_brief(
    brief_id: str,
    body: AckRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """FI acknowledges receipt + intended response.

    DEMO: ack capture only. Downstream consumer (Compliance Tracker)
    is a v2 agent, deferred — we persist and audit, nothing more.
    """
    brief = await _load_brief(session, brief_id)
    now = datetime.now(tz=timezone.utc)
    brief.ack_received_at = now
    brief.ack_payload = {
        "response_codes": body.response_codes,
        "note": body.note,
    }
    brief.status = "ACKED"
    session.add(
        FIBriefAudit(
            brief_id=brief_id,
            event_type="acked",
            event_payload={"response_codes": body.response_codes},
            actor=f"fi:{brief.institution_id}",
        )
    )
    await session.flush()
    await session.commit()
    return {"brief_id": brief_id, "status": "ACKED", "ack_received_at": now.isoformat()}
