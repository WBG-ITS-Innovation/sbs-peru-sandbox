"""Cross-persona handoff + Unit-Head override (P-RESHAPE-5).

* Supervisor / Unit Head create assignments (``assignment:create``).
* Analyst acknowledges assignments in their inbox (``assignment:ack``).
* Unit Head overrides a Supervisor's FIBrief decision
  (``fi_brief:override``) — gated on a 50-char rationale, stricter than
  the 20-char approval gate, because overrides are politically heavier.

Every action lands a ``persona_audit`` row.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.auth.persona_scopes import (
    ASSIGNMENT_ACK,
    ASSIGNMENT_CREATE,
    FI_BRIEF_OVERRIDE,
    primary_persona,
)
from sbs_api.db.models.fi_brief import FIBrief
from sbs_api.db.models.fi_brief_audit import FIBriefAudit
from sbs_api.db.models.persona_assignment import PersonaAssignment
from sbs_api.db.models.persona_audit import PersonaAudit
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.persona import requires_any_scope, requires_scope
from sbs_api.routes._internal_auth import parse_roles_header, verify_internal_secret

router = APIRouter(prefix="/internal/persona", tags=["Internal"])

_ASSIGN = requires_scope(ASSIGNMENT_CREATE)
_ACK = requires_scope(ASSIGNMENT_ACK)
_OVERRIDE = requires_scope(FI_BRIEF_OVERRIDE)
# The inbox is a read of one's own assignments — viewable by any persona
# that can either create or acknowledge a handoff. The target_user_id
# filter (not the role) is what scopes the rows to the caller.
_INBOX_VIEW = requires_any_scope(ASSIGNMENT_ACK, ASSIGNMENT_CREATE)


async def _audit(
    session: AsyncSession,
    *,
    actor: str,
    roles: frozenset[str],
    action: str,
    target_type: str | None,
    target_id: str | None,
    params: dict | None = None,
    rationale: str | None = None,
) -> None:
    session.add(
        PersonaAudit(
            actor_user_id=actor,
            persona=primary_persona(roles) or "unknown",
            action=action,
            target_type=target_type,
            target_id=target_id,
            params=params,
            rationale=rationale,
        )
    )


# --- Assignment create ----------------------------------------------------


class AssignmentRequest(BaseModel):
    source_user_id: str = Field(min_length=1, max_length=128)
    target_user_id: str = Field(min_length=1, max_length=128)
    target_persona: str = Field(min_length=1, max_length=32)
    ref_type: str = Field(pattern="^(PATTERN|COMPLAINT|FIBRIEF)$")
    ref_id: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=2_000)


@router.post(
    "/assignments",
    status_code=201,
    dependencies=[Depends(verify_internal_secret), Depends(_ASSIGN)],
)
async def create_assignment(
    body: AssignmentRequest,
    session: AsyncSession = Depends(get_session),
    x_sbs_role: str | None = Header(default=None, alias="X-SBS-Role"),
) -> dict[str, Any]:
    roles = parse_roles_header(x_sbs_role)
    row = PersonaAssignment(
        source_user_id=body.source_user_id,
        target_user_id=body.target_user_id,
        target_persona=body.target_persona,
        ref_type=body.ref_type,
        ref_id=body.ref_id,
        note=body.note,
    )
    session.add(row)
    await session.flush()
    await _audit(
        session,
        actor=body.source_user_id,
        roles=roles,
        action="assignment-created",
        target_type=body.ref_type,
        target_id=body.ref_id,
        params={"target_user_id": body.target_user_id},
    )
    await session.commit()
    return {"assignment_id": row.assignment_id, "status": "created"}


# --- Inbox + ack ----------------------------------------------------------


@router.get(
    "/assignments/inbox",
    dependencies=[Depends(verify_internal_secret), Depends(_INBOX_VIEW)],
)
async def my_inbox(
    target_user_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(PersonaAssignment)
            .where(PersonaAssignment.target_user_id == target_user_id)
            .where(PersonaAssignment.acknowledged_at.is_(None))
            .order_by(PersonaAssignment.created_at.desc())
        )
    ).scalars().all()
    return {
        "items": [
            {
                "assignment_id": a.assignment_id,
                "source_user_id": a.source_user_id,
                "ref_type": a.ref_type,
                "ref_id": a.ref_id,
                "note": a.note,
                "created_at": a.created_at.isoformat(timespec="seconds"),
            }
            for a in rows
        ],
        "total": len(rows),
    }


class AckRequest(BaseModel):
    actor_user_id: str = Field(min_length=1, max_length=128)


@router.post(
    "/assignments/{assignment_id}/ack",
    status_code=200,
    dependencies=[Depends(verify_internal_secret), Depends(_ACK)],
)
async def ack_assignment(
    assignment_id: int,
    body: AckRequest,
    session: AsyncSession = Depends(get_session),
    x_sbs_role: str | None = Header(default=None, alias="X-SBS-Role"),
) -> dict[str, Any]:
    roles = parse_roles_header(x_sbs_role)
    row = (
        await session.execute(
            select(PersonaAssignment).where(
                PersonaAssignment.assignment_id == assignment_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if row.acknowledged_at is None:
        row.acknowledged_at = datetime.now(tz=timezone.utc)
        await session.flush()
        await _audit(
            session,
            actor=body.actor_user_id,
            roles=roles,
            action="assignment-acked",
            target_type=row.ref_type,
            target_id=row.ref_id,
        )
        await session.commit()
    return {"assignment_id": assignment_id, "status": "acknowledged"}


# --- Unit-Head override (50-char rationale) -------------------------------


class OverrideRequest(BaseModel):
    actor_id: str = Field(min_length=1, max_length=128)
    new_status: str = Field(pattern="^(APPROVED|REJECTED)$")
    rationale: str = Field(
        min_length=50,
        max_length=2_000,
        description=(
            "Why the Supervisor decision is overridden — >= 50 chars "
            "(server-enforced, stricter than the 20-char approval gate)."
        ),
    )


@router.post(
    "/fi_briefs/{brief_id}/override",
    status_code=201,
    dependencies=[Depends(verify_internal_secret), Depends(_OVERRIDE)],
)
async def override_brief_decision(
    brief_id: str,
    body: OverrideRequest,
    session: AsyncSession = Depends(get_session),
    x_sbs_role: str | None = Header(default=None, alias="X-SBS-Role"),
) -> dict[str, Any]:
    """Unit Head overrides a Supervisor's FIBrief decision. The 50-char
    rationale is enforced by Pydantic; the override is double-logged in
    both fi_brief_audit and persona_audit."""
    roles = parse_roles_header(x_sbs_role)
    brief = (
        await session.execute(
            select(FIBrief).where(FIBrief.brief_id == brief_id)
        )
    ).scalar_one_or_none()
    if brief is None:
        raise HTTPException(status_code=404, detail="FIBrief not found")

    prior_status = brief.status
    now = datetime.now(tz=timezone.utc)
    brief.status = body.new_status
    if body.new_status == "APPROVED":
        brief.approved_by = body.actor_id
        brief.approved_at = now
        brief.approval_rationale = body.rationale
    else:
        brief.rejected_by = body.actor_id
        brief.rejected_at = now
        brief.rejection_reason = body.rationale

    session.add(
        FIBriefAudit(
            brief_id=brief_id,
            event_type="unit_head_override",
            event_payload={
                "prior_status": prior_status,
                "new_status": body.new_status,
                "rationale_excerpt": body.rationale[:200],
            },
            actor=body.actor_id,
        )
    )
    await _audit(
        session,
        actor=body.actor_id,
        roles=roles,
        action="fi_brief-override",
        target_type="FIBRIEF",
        target_id=brief_id,
        rationale=body.rationale,
        params={"prior_status": prior_status, "new_status": body.new_status},
    )
    await session.flush()
    await session.commit()
    return {
        "brief_id": brief_id,
        "prior_status": prior_status,
        "new_status": body.new_status,
    }
