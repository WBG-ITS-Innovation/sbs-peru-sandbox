"""Executive tasking + weekly digest actions (P-RESHAPE-8.5).

* POST /v1/internal/exec/tasking — Superintendent requests a deeper look
  (``exec:tasking``). Creates a DEEPER_LOOK ``persona_tasks`` row assigned
  to the Unit Head persona.
* POST /v1/internal/exec/digest/generate — Unit Head generates the weekly
  digest (``digest:generate``). Writes a GENERATED ``digest_audit`` row.
* POST /v1/internal/exec/digest/{digest_id}/acknowledge — Superintendent
  signs it (``digest:acknowledge``). Writes an ACKNOWLEDGED row.

Lives under the exec prefix but is a distinct router from the read-only
exec aggregates. No per-complaint identifier or raw narrative is stored.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.auth.persona_scopes import (
    DIGEST_ACK,
    DIGEST_GENERATE,
    EXEC_TASKING,
    ROLE_UNIT_HEAD,
    primary_persona,
)
from sbs_api.db.models.digest_audit import DigestAudit
from sbs_api.db.models.persona_audit import PersonaAudit
from sbs_api.db.models.persona_task import PersonaTask
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.persona import requires_scope
from sbs_api.routes._internal_auth import verify_internal_secret

router = APIRouter(prefix="/internal/exec", tags=["Exec"])

_TASKING = requires_scope(EXEC_TASKING)
_DIGEST_GEN = requires_scope(DIGEST_GENERATE)
_DIGEST_ACK = requires_scope(DIGEST_ACK)


class TaskingRequest(BaseModel):
    actor_user_id: str = Field(min_length=1, max_length=128)
    ref_type: str = Field(default="PATTERN", max_length=32)
    ref_id: str = Field(min_length=1, max_length=64)
    rationale: str = Field(min_length=30, max_length=2_000)
    assigned_to_user_id: str | None = Field(default=None, max_length=128)


@router.post(
    "/tasking",
    status_code=201,
    dependencies=[Depends(verify_internal_secret)],
)
async def request_deeper_look(
    body: TaskingRequest,
    roles: frozenset[str] = Depends(_TASKING),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    persona = primary_persona(roles) or "unknown"
    task_id = str(uuid.uuid4())
    session.add(
        PersonaTask(
            task_id=task_id,
            created_by_user_id=body.actor_user_id,
            created_by_persona=persona,
            assigned_to_user_id=body.assigned_to_user_id,
            assigned_to_persona=ROLE_UNIT_HEAD,
            task_type="DEEPER_LOOK",
            ref_type=body.ref_type,
            ref_id=body.ref_id,
            rationale=body.rationale,
            state="OPEN",
        )
    )
    session.add(
        PersonaAudit(
            actor_user_id=body.actor_user_id,
            persona=persona,
            action="deeper-look-requested",
            target_type=body.ref_type,
            target_id=body.ref_id,
            rationale=body.rationale,
        )
    )
    await session.commit()
    return {"task_id": task_id, "state": "OPEN", "task_type": "DEEPER_LOOK"}


class DigestGenerateRequest(BaseModel):
    actor_user_id: str = Field(min_length=1, max_length=128)
    summary: str | None = Field(default=None, max_length=4_000)


@router.post(
    "/digest/generate",
    status_code=201,
    dependencies=[Depends(verify_internal_secret)],
)
async def generate_weekly_digest(
    body: DigestGenerateRequest,
    roles: frozenset[str] = Depends(_DIGEST_GEN),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    persona = primary_persona(roles) or "unknown"
    digest_id = str(uuid.uuid4())
    session.add(
        DigestAudit(
            digest_id=digest_id,
            event_type="GENERATED",
            actor_user_id=body.actor_user_id,
            persona=persona,
            summary=body.summary,
        )
    )
    await session.commit()
    return {"digest_id": digest_id, "event_type": "GENERATED"}


class DigestAckRequest(BaseModel):
    actor_user_id: str = Field(min_length=1, max_length=128)


@router.post(
    "/digest/{digest_id}/acknowledge",
    status_code=201,
    dependencies=[Depends(verify_internal_secret)],
)
async def acknowledge_digest(
    digest_id: str,
    body: DigestAckRequest,
    roles: frozenset[str] = Depends(_DIGEST_ACK),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    persona = primary_persona(roles) or "unknown"
    generated = (
        await session.execute(
            select(DigestAudit)
            .where(DigestAudit.digest_id == digest_id)
            .where(DigestAudit.event_type == "GENERATED")
        )
    ).first()
    if generated is None:
        raise HTTPException(status_code=404, detail="Digest not found")
    session.add(
        DigestAudit(
            digest_id=digest_id,
            event_type="ACKNOWLEDGED",
            actor_user_id=body.actor_user_id,
            persona=persona,
        )
    )
    await session.commit()
    return {"digest_id": digest_id, "event_type": "ACKNOWLEDGED"}
