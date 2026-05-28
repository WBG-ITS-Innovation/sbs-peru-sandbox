"""Sector-broadcast dual approval + reject (P-RESHAPE-6).

A sector broadcast is a sector-level policy action, so it carries a
DUAL-approval gate:

* ``approve_primary``   — any user with ``sector_broadcast:approve_primary``
  (Supervisor or Unit Head). 50-char rationale.
* ``approve_secondary`` — Unit Head OR Superintendent
  (``sector_broadcast:approve_secondary``). 50-char rationale. Must be a
  DIFFERENT user from the primary approver.

Only after BOTH approvals does the broadcast deliver to every target FI.
Each approval lands a ``sector_broadcast_audit`` row.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.auth.persona_scopes import (
    SECTOR_BROADCAST_APPROVE_PRIMARY,
    SECTOR_BROADCAST_APPROVE_SECONDARY,
)
from sbs_api.db.models.sector_broadcast import SectorBroadcast, SectorBroadcastAudit
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.persona import requires_scope
from sbs_api.routes._internal_auth import verify_internal_secret
from sbs_api.webhooks.sector_broadcast_delivery import deliver_sector_broadcast

router = APIRouter(prefix="/internal/sector_broadcast", tags=["Internal"])

_PRIMARY = requires_scope(SECTOR_BROADCAST_APPROVE_PRIMARY)
_SECONDARY = requires_scope(SECTOR_BROADCAST_APPROVE_SECONDARY)


class _ApprovalRequest(BaseModel):
    actor_id: str = Field(min_length=1, max_length=128)
    rationale: str = Field(
        min_length=50,
        max_length=2_000,
        description="Sector-broadcast approvals require >= 50 chars (server-enforced).",
    )


class _RejectRequest(BaseModel):
    actor_id: str = Field(min_length=1, max_length=128)
    rationale: str = Field(min_length=50, max_length=2_000)


async def _load(session: AsyncSession, broadcast_id: str) -> SectorBroadcast:
    b = (
        await session.execute(
            select(SectorBroadcast).where(
                SectorBroadcast.broadcast_id == broadcast_id
            )
        )
    ).scalar_one_or_none()
    if b is None:
        raise HTTPException(status_code=404, detail="SectorBroadcast not found")
    return b


@router.post(
    "/{broadcast_id}/approve_primary",
    status_code=201,
    dependencies=[Depends(verify_internal_secret), Depends(_PRIMARY)],
)
async def approve_primary(
    broadcast_id: str,
    body: _ApprovalRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    b = await _load(session, broadcast_id)
    if b.status != "AWAITING_DUAL_APPROVAL":
        raise HTTPException(
            status_code=409, detail=f"broadcast is {b.status}, cannot primary-approve"
        )
    now = datetime.now(tz=timezone.utc)
    b.primary_approver = body.actor_id
    b.primary_approved_at = now
    b.primary_rationale = body.rationale
    b.status = "AWAITING_SECONDARY_APPROVAL"
    session.add(
        SectorBroadcastAudit(
            broadcast_id=broadcast_id,
            event_type="primary_approved",
            actor=body.actor_id,
            rationale=body.rationale[:200],
        )
    )
    await session.flush()
    await session.commit()
    return {"broadcast_id": broadcast_id, "status": b.status}


@router.post(
    "/{broadcast_id}/approve_secondary",
    status_code=201,
    dependencies=[Depends(verify_internal_secret), Depends(_SECONDARY)],
)
async def approve_secondary(
    broadcast_id: str,
    body: _ApprovalRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    b = await _load(session, broadcast_id)
    if b.status != "AWAITING_SECONDARY_APPROVAL":
        raise HTTPException(
            status_code=409,
            detail=f"broadcast is {b.status}, cannot secondary-approve",
        )
    # Two distinct approvers — the secondary cannot be the primary.
    if body.actor_id == b.primary_approver:
        raise HTTPException(
            status_code=409,
            detail="secondary approver must differ from the primary approver",
        )
    now = datetime.now(tz=timezone.utc)
    b.secondary_approver = body.actor_id
    b.secondary_approved_at = now
    b.secondary_rationale = body.rationale
    b.status = "APPROVED"
    session.add(
        SectorBroadcastAudit(
            broadcast_id=broadcast_id,
            event_type="secondary_approved",
            actor=body.actor_id,
            rationale=body.rationale[:200],
        )
    )
    await session.flush()

    # Dual approval complete → deliver to every target FI.
    outcome = await deliver_sector_broadcast(session, broadcast_id=broadcast_id)
    await session.commit()
    return {
        "broadcast_id": broadcast_id,
        "status": outcome.status,
        "delivered": outcome.delivered,
        "failed": outcome.failed,
    }


@router.post(
    "/{broadcast_id}/reject",
    status_code=201,
    dependencies=[Depends(verify_internal_secret), Depends(_PRIMARY)],
)
async def reject_broadcast(
    broadcast_id: str,
    body: _RejectRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    b = await _load(session, broadcast_id)
    if b.status not in {"AWAITING_DUAL_APPROVAL", "AWAITING_SECONDARY_APPROVAL"}:
        raise HTTPException(
            status_code=409, detail=f"broadcast is {b.status}, cannot reject"
        )
    now = datetime.now(tz=timezone.utc)
    b.status = "REJECTED"
    b.rejected_by = body.actor_id
    b.rejected_at = now
    session.add(
        SectorBroadcastAudit(
            broadcast_id=broadcast_id,
            event_type="rejected",
            actor=body.actor_id,
            rationale=body.rationale[:200],
        )
    )
    await session.flush()
    await session.commit()
    return {"broadcast_id": broadcast_id, "status": "REJECTED"}
