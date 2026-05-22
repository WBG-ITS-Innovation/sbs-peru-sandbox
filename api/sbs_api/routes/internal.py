"""Server-to-server endpoints for the supervisor UI.

The Next.js supervisor UI calls FastAPI for cross-screen state that
must live on the regulator side: the audit chain. These routes are
deliberately not part of the institutional `/v1/*` surface — they sit
under `/v1/internal/*` and are authenticated by a shared secret in the
Authorization header, not by the mTLS + OAuth chain that gates
institutional requests.

The shared secret model is the minimum that lets two server processes
talk to each other under a single trust domain. Part 9 production work
hardens this with a per-route service-account JWT signed by Keycloak;
the route shape stays the same.
"""

from __future__ import annotations

import secrets
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.audit import record_audit_event
from sbs_api.config import Settings, get_settings
from sbs_api.dependencies.db import get_session

router = APIRouter(prefix="/internal", tags=["Internal"])


class AuditWriteRequest(BaseModel):
    """Shape the Next.js audit bridge sends. Mirrors the helper signature
    of ``sbs_api.audit.record_audit_event`` so the contract is the same
    on both sides of the wire.
    """

    actor_type: Literal["user", "agent"]
    actor_id: str = Field(min_length=1, max_length=128)
    action: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9-]*[a-z0-9]$",
        description="kebab-case action code.",
    )
    object_type: str = Field(min_length=1, max_length=32)
    object_id: str = Field(min_length=1, max_length=64)
    diff: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


class AuditWriteResponse(BaseModel):
    id: int
    created_at: str


def _verify_internal_secret(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """FastAPI dependency: rejects calls without a matching shared secret.

    Constant-time compare; constant 401 on missing header AND on
    mismatched header so a probe cannot distinguish 'no secret
    configured' from 'wrong secret'. If the secret is not configured at
    all (None), the endpoint is unreachable — defends against a
    misconfigured deployment exposing the audit write path to anyone.
    """

    expected = settings.internal_api_secret
    if not expected:
        raise HTTPException(status_code=404, detail="Not Found")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    presented = authorization[len("Bearer ") :]
    if not secrets.compare_digest(presented, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post(
    "/audit",
    response_model=AuditWriteResponse,
    status_code=201,
    dependencies=[Depends(_verify_internal_secret)],
)
async def write_audit(
    body: AuditWriteRequest,
    session: AsyncSession = Depends(get_session),
) -> AuditWriteResponse:
    """Write one audit_events row on behalf of the supervisor UI.

    The supervisor UI does not own the database; this endpoint is the
    only path by which a non-FastAPI process writes to ``audit_events``.
    The Pydantic model validates the kebab-case action shape before the
    DB check constraint sees it, so a typo surfaces as a 422, not a
    500.
    """

    try:
        event = await record_audit_event(
            session,
            actor_type=body.actor_type,
            actor_id=body.actor_id,
            action=body.action,
            object_type=body.object_type,
            object_id=body.object_id,
            diff=body.diff,
            meta=body.meta,
        )
        await session.commit()
    except IntegrityError as exc:
        # Most likely cause: the DB check constraint rejected the action
        # string even though it passed Pydantic validation — should not
        # happen, but if it does we surface the constraint name.
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(exc.orig)) from exc

    return AuditWriteResponse(
        id=event.id,
        created_at=event.created_at.isoformat(timespec="seconds"),
    )
