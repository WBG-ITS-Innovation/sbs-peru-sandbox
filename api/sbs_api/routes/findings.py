"""Findings list + detail + draft-save + send-to-approvals endpoints.

All four routes share the ``/v1/internal`` prefix and the shared-
secret + role-header auth. Role scoping is enforced in the request
handler (ADR 0043 will lift this to a declarative table when WS7
lands).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.audit import record_audit_event
from sbs_api.db.models.complaint_narrative_draft import ComplaintNarrativeDraft
from sbs_api.db.models.pending_approval import PendingApproval
from sbs_api.dependencies.db import get_session
from sbs_api.findings import (
    FindingsFilters,
    build_finding_detail,
    build_findings_list,
)
from sbs_api.findings.builder import default_filters_for_role
from sbs_api.routes._internal_auth import current_roles, verify_internal_secret
from sbs_api.sse import get_bus

router = APIRouter(prefix="/internal", tags=["Internal"])


# -- GET /v1/internal/findings ----------------------------------------------


@router.get(
    "/findings",
    dependencies=[Depends(verify_internal_secret)],
)
async def get_findings(
    institution: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    source: str | None = Query(default=None),
    classification: str | None = Query(default=None),
    confidence_band: Literal["low", "medium", "high"] | None = Query(default=None),
    from_received_at: datetime | None = Query(default=None),
    to_received_at: datetime | None = Query(default=None),
    use_defaults: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
    roles: frozenset[str] = Depends(current_roles),
) -> dict[str, Any]:
    explicit = FindingsFilters(
        institution_id=institution,
        severity=severity,
        source=source,
        classification=classification,
        confidence_band=confidence_band,
        from_received_at=from_received_at,
        to_received_at=to_received_at,
    )
    # If the caller passed nothing, apply role defaults so an empty
    # query string still returns "the Conduct Analyst's high-confidence last 24h".
    no_explicit = explicit == FindingsFilters()
    filters = default_filters_for_role(roles) if (no_explicit and use_defaults) else explicit
    return await build_findings_list(session, roles=roles, filters=filters)


# -- GET /v1/internal/findings/{id} -----------------------------------------


@router.get(
    "/findings/{complaint_id}",
    dependencies=[Depends(verify_internal_secret)],
)
async def get_finding_detail(
    complaint_id: str,
    session: AsyncSession = Depends(get_session),
    roles: frozenset[str] = Depends(current_roles),
) -> dict[str, Any]:
    detail = await build_finding_detail(
        session, complaint_id=complaint_id, roles=roles
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    return detail


# -- POST /v1/internal/findings/{id}/draft ----------------------------------


class DraftSaveRequest(BaseModel):
    after_text: str = Field(min_length=1, max_length=10_000)
    actor_id: str = Field(min_length=1, max_length=128)
    agent_run_id: str | None = Field(default=None, max_length=36)


class DraftSaveResponse(BaseModel):
    id: int
    created_at: str
    audit_event_id: int


@router.post(
    "/findings/{complaint_id}/draft",
    response_model=DraftSaveResponse,
    status_code=201,
    dependencies=[Depends(verify_internal_secret)],
)
async def save_draft(
    complaint_id: str,
    body: DraftSaveRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftSaveResponse:
    # Find the most-recent prior draft, or the agent-drafted text from
    # agent_runs, to record as before_text.
    prior = (
        await session.execute(
            select(ComplaintNarrativeDraft)
            .where(ComplaintNarrativeDraft.complaint_id == complaint_id)
            .order_by(desc(ComplaintNarrativeDraft.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    before_text = prior.after_text if prior else ""

    draft = ComplaintNarrativeDraft(
        complaint_id=complaint_id,
        agent_run_id=body.agent_run_id,
        created_by=body.actor_id,
        before_text=before_text,
        after_text=body.after_text,
    )
    session.add(draft)
    await session.flush()

    audit = await record_audit_event(
        session,
        actor_type="user",
        actor_id=body.actor_id,
        action="edit-draft-narrative",
        object_type="complaint",
        object_id=complaint_id,
        diff={
            "before_excerpt": before_text[:200],
            "after_excerpt": body.after_text[:200],
        },
        meta={
            "complaint_id": complaint_id,
            "draft_id": draft.id,
            "agent_run_id": body.agent_run_id,
        },
    )
    await session.flush()
    await session.commit()

    await get_bus().publish(
        "findings",
        "narrative.edited",
        f'{{"complaint_id":"{complaint_id}","draft_id":{draft.id}}}',
    )

    return DraftSaveResponse(
        id=draft.id,
        created_at=draft.created_at.isoformat(timespec="seconds"),
        audit_event_id=audit.id,
    )


# -- POST /v1/internal/findings/{id}/send-to-approvals ----------------------


class SendToApprovalsRequest(BaseModel):
    severity: Literal["low", "medium", "high", "critical"]
    actor_id: str = Field(min_length=1, max_length=128)
    agent_run_id: str | None = Field(default=None, max_length=36)


class SendToApprovalsResponse(BaseModel):
    id: int
    status: str
    created_at: str
    audit_event_id: int
    idempotent_replay: bool


@router.post(
    "/findings/{complaint_id}/send-to-approvals",
    response_model=SendToApprovalsResponse,
    status_code=201,
    dependencies=[Depends(verify_internal_secret)],
)
async def send_to_approvals(
    complaint_id: str,
    body: SendToApprovalsRequest,
    session: AsyncSession = Depends(get_session),
) -> SendToApprovalsResponse:
    # Application-level idempotency: if a pending row already exists
    # for this complaint, return it instead of creating a duplicate.
    existing = (
        await session.execute(
            select(PendingApproval)
            .where(PendingApproval.complaint_id == complaint_id)
            .where(PendingApproval.status == "pending")
            .order_by(desc(PendingApproval.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return SendToApprovalsResponse(
            id=existing.id,
            status=existing.status,
            created_at=existing.created_at.isoformat(timespec="seconds"),
            audit_event_id=0,
            idempotent_replay=True,
        )

    pending = PendingApproval(
        complaint_id=complaint_id,
        agent_run_id=body.agent_run_id,
        status="pending",
        severity=body.severity,
        created_by=body.actor_id,
    )
    session.add(pending)
    await session.flush()

    audit = await record_audit_event(
        session,
        actor_type="user",
        actor_id=body.actor_id,
        action="send-to-approvals",
        object_type="complaint",
        object_id=complaint_id,
        meta={
            "complaint_id": complaint_id,
            "pending_approval_id": pending.id,
            "severity": body.severity,
            "agent_run_id": body.agent_run_id,
        },
    )
    await session.flush()
    await session.commit()

    await get_bus().publish(
        "approvals",
        "approval.pending",
        f'{{"complaint_id":"{complaint_id}","pending_approval_id":{pending.id}}}',
    )

    return SendToApprovalsResponse(
        id=pending.id,
        status=pending.status,
        created_at=pending.created_at.isoformat(timespec="seconds"),
        audit_event_id=audit.id,
        idempotent_replay=False,
    )
