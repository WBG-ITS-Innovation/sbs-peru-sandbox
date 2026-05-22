"""Approvals list + detail + four decision endpoints.

The four decisions write to different downstream tables:

* approve         → supervisory_observations + audit
* approve-with-edits → supervisory_observations + agent_feedback + audit
* reject          → agent_feedback + audit (rationale >= 20 chars
                    enforced at Pydantic AND at the DB check
                    constraint)
* send-back-to-analyst → pending_approvals.status = 'sent_back' + audit

All four are idempotent: a duplicate POST on a non-pending row returns
the existing decision with ``idempotent_replay=true``. A double-click
on demo day does not create a second row.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.approvals import build_approval_detail, build_approvals_queue
from sbs_api.audit import record_audit_event
from sbs_api.db.models.agent_feedback import AgentFeedback
from sbs_api.db.models.pending_approval import PendingApproval
from sbs_api.db.models.supervisory_observation import SupervisoryObservation
from sbs_api.dependencies.db import get_session
from sbs_api.routes._internal_auth import (
    current_roles,
    require_any_role,
    verify_internal_secret,
)
from sbs_api.sse import get_bus

router = APIRouter(prefix="/internal", tags=["Internal"])


# Approvals queue + detail require head OR analyst role per ADR 0040
# §D7's demo outline (the supervisor scope alone does not subscribe).
_HEAD_OR_ANALYST = require_any_role(
    {"sbs:conduct:analyst", "sbs:conduct:head"}
)
_HEAD_ONLY = require_any_role({"sbs:conduct:head"})


# --- GET /v1/internal/approvals -------------------------------------------


@router.get(
    "/approvals",
    dependencies=[Depends(verify_internal_secret), Depends(_HEAD_OR_ANALYST)],
)
async def get_approvals_queue(
    session: AsyncSession = Depends(get_session),
    roles: frozenset[str] = Depends(current_roles),
) -> dict[str, Any]:
    return await build_approvals_queue(session, roles=roles)


# --- GET /v1/internal/approvals/{id} --------------------------------------


@router.get(
    "/approvals/{pending_approval_id}",
    dependencies=[Depends(verify_internal_secret), Depends(_HEAD_OR_ANALYST)],
)
async def get_approval_detail(
    pending_approval_id: int,
    session: AsyncSession = Depends(get_session),
    roles: frozenset[str] = Depends(current_roles),
) -> dict[str, Any]:
    detail = await build_approval_detail(
        session, pending_approval_id=pending_approval_id, roles=roles
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return detail


# --- POST decisions: shared helpers ---------------------------------------


class _DecisionResponse(BaseModel):
    pending_approval_id: int
    status: str
    decision_action: str
    decided_at: str | None
    audit_event_id: int
    observation_id: int | None = None
    feedback_id: int | None = None
    idempotent_replay: bool


async def _load_pending(
    session: AsyncSession, pending_approval_id: int
) -> PendingApproval:
    row = (
        await session.execute(
            select(PendingApproval).where(PendingApproval.id == pending_approval_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    return row


def _idempotent_replay(
    pending: PendingApproval, expected_action: str
) -> _DecisionResponse | None:
    """If this approval already has a decision matching the action,
    return the existing decision wrapped as a replay. Mismatched action
    on an already-decided row is a 409 — the caller is racing a
    different decision."""

    if pending.status == "pending":
        return None
    if pending.decision_action != expected_action:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Approval already decided as {pending.decision_action!r}, "
                f"cannot {expected_action!r}"
            ),
        )
    return _DecisionResponse(
        pending_approval_id=pending.id,
        status=pending.status,
        decision_action=pending.decision_action or expected_action,
        decided_at=pending.decided_at.isoformat(timespec="seconds")
        if pending.decided_at
        else None,
        audit_event_id=0,
        idempotent_replay=True,
    )


# --- POST /approvals/{id}/approve -----------------------------------------


class ApproveRequest(BaseModel):
    actor_id: str = Field(min_length=1, max_length=128)


@router.post(
    "/approvals/{pending_approval_id}/approve",
    response_model=_DecisionResponse,
    status_code=201,
    dependencies=[Depends(verify_internal_secret), Depends(_HEAD_ONLY)],
)
async def approve(
    pending_approval_id: int,
    body: ApproveRequest,
    session: AsyncSession = Depends(get_session),
) -> _DecisionResponse:
    pending = await _load_pending(session, pending_approval_id)
    replay = _idempotent_replay(pending, "approve")
    if replay:
        return replay

    narrative = await _resolve_narrative(session, pending.complaint_id)
    now = datetime.now(tz=timezone.utc)
    observation = SupervisoryObservation(
        complaint_id=pending.complaint_id,
        agent_run_id=pending.agent_run_id,
        pending_approval_id=pending.id,
        narrative=narrative,
        approved_by=body.actor_id,
        agent_version=None,
        model_versions=None,
    )
    session.add(observation)
    pending.status = "approved"
    pending.decided_at = now
    pending.decided_by = body.actor_id
    pending.decision_action = "approve"
    await session.flush()

    audit = await record_audit_event(
        session,
        actor_type="user",
        actor_id=body.actor_id,
        action="approve-finding",
        object_type="approval",
        object_id=str(pending.id),
        meta=_decision_meta(
            pending,
            "approve",
            observation_id=observation.id,
            feedback_id=None,
            rationale=None,
            edit_diff=None,
        ),
    )
    await session.flush()
    await session.commit()

    await _publish_decision(pending.id, "approve")

    return _DecisionResponse(
        pending_approval_id=pending.id,
        status="approved",
        decision_action="approve",
        decided_at=now.isoformat(timespec="seconds"),
        audit_event_id=audit.id,
        observation_id=observation.id,
        idempotent_replay=False,
    )


# --- POST /approvals/{id}/approve-with-edits ------------------------------


class ApproveWithEditsRequest(BaseModel):
    actor_id: str = Field(min_length=1, max_length=128)
    edited_narrative: str = Field(min_length=1, max_length=10_000)
    rationale: str = Field(
        min_length=20, max_length=2_000,
        description="Why the edit was made — >= 20 chars (server-enforced).",
    )


@router.post(
    "/approvals/{pending_approval_id}/approve-with-edits",
    response_model=_DecisionResponse,
    status_code=201,
    dependencies=[Depends(verify_internal_secret), Depends(_HEAD_ONLY)],
)
async def approve_with_edits(
    pending_approval_id: int,
    body: ApproveWithEditsRequest,
    session: AsyncSession = Depends(get_session),
) -> _DecisionResponse:
    pending = await _load_pending(session, pending_approval_id)
    replay = _idempotent_replay(pending, "approve-with-edits")
    if replay:
        return replay

    before_text = await _resolve_narrative(session, pending.complaint_id)
    edit_diff = {"before": before_text, "after": body.edited_narrative}
    now = datetime.now(tz=timezone.utc)

    observation = SupervisoryObservation(
        complaint_id=pending.complaint_id,
        agent_run_id=pending.agent_run_id,
        pending_approval_id=pending.id,
        narrative=body.edited_narrative,
        approved_by=body.actor_id,
    )
    feedback = AgentFeedback(
        complaint_id=pending.complaint_id,
        agent_run_id=pending.agent_run_id,
        pending_approval_id=pending.id,
        decision="approve-with-edits",
        rationale=body.rationale,
        edit_diff=edit_diff,
        recorded_by=body.actor_id,
    )
    session.add_all([observation, feedback])
    pending.status = "approved"
    pending.decided_at = now
    pending.decided_by = body.actor_id
    pending.decision_action = "approve-with-edits"
    pending.decision_rationale = body.rationale
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(exc.orig)) from exc

    audit = await record_audit_event(
        session,
        actor_type="user",
        actor_id=body.actor_id,
        action="approve-with-edits-finding",
        object_type="approval",
        object_id=str(pending.id),
        diff={
            "before_excerpt": before_text[:200],
            "after_excerpt": body.edited_narrative[:200],
        },
        meta=_decision_meta(
            pending,
            "approve-with-edits",
            observation_id=observation.id,
            feedback_id=feedback.id,
            rationale=body.rationale,
            edit_diff=edit_diff,
        ),
    )
    await session.flush()
    await session.commit()

    await _publish_decision(pending.id, "approve-with-edits")

    return _DecisionResponse(
        pending_approval_id=pending.id,
        status="approved",
        decision_action="approve-with-edits",
        decided_at=now.isoformat(timespec="seconds"),
        audit_event_id=audit.id,
        observation_id=observation.id,
        feedback_id=feedback.id,
        idempotent_replay=False,
    )


# --- POST /approvals/{id}/reject ------------------------------------------


class RejectRequest(BaseModel):
    actor_id: str = Field(min_length=1, max_length=128)
    rationale: str = Field(
        min_length=20, max_length=2_000,
        description="Why the finding is rejected — >= 20 chars (server-enforced).",
    )


@router.post(
    "/approvals/{pending_approval_id}/reject",
    response_model=_DecisionResponse,
    status_code=201,
    dependencies=[Depends(verify_internal_secret), Depends(_HEAD_ONLY)],
)
async def reject(
    pending_approval_id: int,
    body: RejectRequest,
    session: AsyncSession = Depends(get_session),
) -> _DecisionResponse:
    pending = await _load_pending(session, pending_approval_id)
    replay = _idempotent_replay(pending, "reject")
    if replay:
        return replay

    now = datetime.now(tz=timezone.utc)
    feedback = AgentFeedback(
        complaint_id=pending.complaint_id,
        agent_run_id=pending.agent_run_id,
        pending_approval_id=pending.id,
        decision="reject",
        rationale=body.rationale,
        edit_diff=None,
        recorded_by=body.actor_id,
    )
    session.add(feedback)
    pending.status = "rejected"
    pending.decided_at = now
    pending.decided_by = body.actor_id
    pending.decision_action = "reject"
    pending.decision_rationale = body.rationale
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(exc.orig)) from exc

    audit = await record_audit_event(
        session,
        actor_type="user",
        actor_id=body.actor_id,
        action="reject-finding",
        object_type="approval",
        object_id=str(pending.id),
        meta=_decision_meta(
            pending,
            "reject",
            observation_id=None,
            feedback_id=feedback.id,
            rationale=body.rationale,
            edit_diff=None,
        ),
    )
    await session.flush()
    await session.commit()

    await _publish_decision(pending.id, "reject")

    return _DecisionResponse(
        pending_approval_id=pending.id,
        status="rejected",
        decision_action="reject",
        decided_at=now.isoformat(timespec="seconds"),
        audit_event_id=audit.id,
        feedback_id=feedback.id,
        idempotent_replay=False,
    )


# --- POST /approvals/{id}/send-back ---------------------------------------


class SendBackRequest(BaseModel):
    actor_id: str = Field(min_length=1, max_length=128)
    note: str = Field(min_length=1, max_length=2_000)


@router.post(
    "/approvals/{pending_approval_id}/send-back",
    response_model=_DecisionResponse,
    status_code=201,
    dependencies=[Depends(verify_internal_secret), Depends(_HEAD_ONLY)],
)
async def send_back(
    pending_approval_id: int,
    body: SendBackRequest,
    session: AsyncSession = Depends(get_session),
) -> _DecisionResponse:
    pending = await _load_pending(session, pending_approval_id)
    replay = _idempotent_replay(pending, "send-back-to-analyst")
    if replay:
        return replay

    now = datetime.now(tz=timezone.utc)
    pending.status = "sent_back"
    pending.decided_at = now
    pending.decided_by = body.actor_id
    pending.decision_action = "send-back-to-analyst"
    pending.decision_rationale = body.note
    await session.flush()

    audit = await record_audit_event(
        session,
        actor_type="user",
        actor_id=body.actor_id,
        action="send-back-finding",
        object_type="approval",
        object_id=str(pending.id),
        meta=_decision_meta(
            pending,
            "send-back-to-analyst",
            observation_id=None,
            feedback_id=None,
            rationale=body.note,
            edit_diff=None,
        ),
    )
    await session.flush()
    await session.commit()

    await _publish_decision(pending.id, "send-back-to-analyst")

    return _DecisionResponse(
        pending_approval_id=pending.id,
        status="sent_back",
        decision_action="send-back-to-analyst",
        decided_at=now.isoformat(timespec="seconds"),
        audit_event_id=audit.id,
        idempotent_replay=False,
    )


# --- Helpers --------------------------------------------------------------


async def _resolve_narrative(session: AsyncSession, complaint_id: str) -> str:
    """The narrative to approve — latest narrative-drafter output if
    present, otherwise the complaint description text."""

    from sqlalchemy import desc as sa_desc

    from sbs_api.db.models.agent_run import AgentRun
    from sbs_api.db.models.complaint import ComplaintRecord
    from sbs_api.db.models.complaint_narrative_draft import ComplaintNarrativeDraft

    # Prefer the latest analyst-edited draft if there is one.
    latest_draft = (
        await session.execute(
            select(ComplaintNarrativeDraft)
            .where(ComplaintNarrativeDraft.complaint_id == complaint_id)
            .order_by(sa_desc(ComplaintNarrativeDraft.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_draft:
        return latest_draft.after_text

    drafter = (
        await session.execute(
            select(AgentRun)
            .where(AgentRun.complaint_id == complaint_id)
            .where(AgentRun.agent_name == "narrative-drafter")
            .order_by(sa_desc(AgentRun.started_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if drafter and drafter.final_output:
        text = drafter.final_output.get("draft_text")
        if text:
            return text

    complaint = (
        await session.execute(
            select(ComplaintRecord).where(
                ComplaintRecord.complaint_id == complaint_id
            )
        )
    ).scalar_one_or_none()
    return complaint.description_text if complaint else ""


def _decision_meta(
    pending: PendingApproval,
    decision_action: str,
    *,
    observation_id: int | None,
    feedback_id: int | None,
    rationale: str | None,
    edit_diff: dict | None,
) -> dict[str, Any]:
    """Audit-row meta payload. Same shape for all four actions so the
    WS6 Audit screen renders them uniformly. Test the shape via
    tests/integration/test_findings_endpoints.py::test_decision_audit_contract
    (lands with the findings test suite under WS5's umbrella)."""

    return {
        "pending_approval_id": pending.id,
        "complaint_id": pending.complaint_id,
        "agent_run_id": pending.agent_run_id,
        "decision_action": decision_action,
        "observation_id": observation_id,
        "feedback_id": feedback_id,
        "severity": pending.severity,
        "rationale_excerpt": (rationale or "")[:200] or None,
        "edit_diff": edit_diff,
    }


async def _publish_decision(pending_approval_id: int, action: str) -> None:
    import json

    await get_bus().publish(
        "approvals",
        "approval.decided",
        json.dumps(
            {"pending_approval_id": pending_approval_id, "decision_action": action}
        ),
    )
