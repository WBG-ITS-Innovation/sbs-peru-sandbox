"""Task inbox/outbox (P-RESHAPE-8.5).

Every persona sees tasks assigned to them (inbox) and tasks they created
for others (outbox), backed by ``persona_tasks``. The ack / complete /
decline transitions are callable only by the assigned persona (or the
specifically-named assignee). Decline requires a 30-char rationale.

Authoritative table note: ``persona_tasks`` owns the action-surface task
lifecycle. The older ``persona_assignments`` table (P-RESHAPE-5) remains
the record for the ``/v1/internal/persona/assignments`` ack-only handoff
and is not joined here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.auth.persona_scopes import primary_persona
from sbs_api.db.models.persona_audit import PersonaAudit
from sbs_api.db.models.persona_task import PersonaTask
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.persona import requires_authenticated_persona
from sbs_api.routes._internal_auth import verify_internal_secret

router = APIRouter(prefix="/internal/cockpit/tasks", tags=["Cockpit"])


def _serialize(t: PersonaTask) -> dict[str, Any]:
    return {
        "task_id": t.task_id,
        "created_at": t.created_at.isoformat(timespec="seconds"),
        "created_by_user_id": t.created_by_user_id,
        "created_by_persona": t.created_by_persona,
        "assigned_to_user_id": t.assigned_to_user_id,
        "assigned_to_persona": t.assigned_to_persona,
        "task_type": t.task_type,
        "ref_type": t.ref_type,
        "ref_id": t.ref_id,
        "rationale": t.rationale,
        "state": t.state,
        "response": t.response,
    }


@router.get(
    "/inbox",
    dependencies=[Depends(verify_internal_secret)],
)
async def inbox(
    user_id: str = Query(min_length=1),
    roles: frozenset[str] = Depends(requires_authenticated_persona),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Tasks directed at the caller: either named to ``user_id`` or
    broadcast to the caller's persona (assigned_to_user_id IS NULL)."""
    persona = primary_persona(roles) or "unknown"
    rows = (
        await session.execute(
            select(PersonaTask)
            .where(
                or_(
                    PersonaTask.assigned_to_user_id == user_id,
                    (PersonaTask.assigned_to_user_id.is_(None))
                    & (PersonaTask.assigned_to_persona == persona),
                )
            )
            .order_by(PersonaTask.created_at.desc())
        )
    ).scalars().all()
    return {"items": [_serialize(t) for t in rows], "total": len(rows)}


@router.get(
    "/outbox",
    dependencies=[Depends(verify_internal_secret)],
)
async def outbox(
    user_id: str = Query(min_length=1),
    roles: frozenset[str] = Depends(requires_authenticated_persona),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Tasks the caller created for others."""
    rows = (
        await session.execute(
            select(PersonaTask)
            .where(PersonaTask.created_by_user_id == user_id)
            .order_by(PersonaTask.created_at.desc())
        )
    ).scalars().all()
    return {"items": [_serialize(t) for t in rows], "total": len(rows)}


# --- Transitions ----------------------------------------------------------


class ActorRequest(BaseModel):
    actor_user_id: str = Field(min_length=1, max_length=128)
    response: str | None = Field(default=None, max_length=2_000)


class DeclineRequest(BaseModel):
    actor_user_id: str = Field(min_length=1, max_length=128)
    rationale: str = Field(min_length=30, max_length=2_000)


async def _load_task_for_actor(
    session: AsyncSession,
    task_id: str,
    actor_user_id: str,
    roles: frozenset[str],
) -> PersonaTask:
    """Load the task and authorise the caller as its assignee. 404 when
    absent; 403 when the caller is neither the named assignee nor a member
    of the assigned persona."""
    task = (
        await session.execute(
            select(PersonaTask).where(PersonaTask.task_id == task_id)
        )
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    persona = primary_persona(roles)
    is_assignee = (
        task.assigned_to_user_id is not None
        and task.assigned_to_user_id == actor_user_id
    )
    is_persona_match = persona is not None and persona == task.assigned_to_persona
    if not (is_assignee or is_persona_match):
        raise HTTPException(status_code=403, detail="Forbidden")
    return task


async def _audit(
    session: AsyncSession,
    *,
    actor: str,
    roles: frozenset[str],
    action: str,
    task: PersonaTask,
    rationale: str | None = None,
) -> None:
    session.add(
        PersonaAudit(
            actor_user_id=actor,
            persona=primary_persona(roles) or "unknown",
            action=action,
            target_type="TASK",
            target_id=task.task_id,
            params={"task_type": task.task_type},
            rationale=rationale,
        )
    )


@router.post(
    "/{task_id}/ack",
    status_code=200,
    dependencies=[Depends(verify_internal_secret)],
)
async def ack_task(
    task_id: str,
    body: ActorRequest,
    roles: frozenset[str] = Depends(requires_authenticated_persona),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    task = await _load_task_for_actor(session, task_id, body.actor_user_id, roles)
    if task.state == "OPEN":
        task.state = "ACKED"
        task.acked_at = datetime.now(tz=timezone.utc)
        await _audit(
            session, actor=body.actor_user_id, roles=roles, action="task-acked", task=task
        )
        await session.commit()
    return {"task_id": task_id, "state": task.state}


@router.post(
    "/{task_id}/complete",
    status_code=200,
    dependencies=[Depends(verify_internal_secret)],
)
async def complete_task(
    task_id: str,
    body: ActorRequest,
    roles: frozenset[str] = Depends(requires_authenticated_persona),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    task = await _load_task_for_actor(session, task_id, body.actor_user_id, roles)
    if task.state not in ("COMPLETED", "DECLINED"):
        task.state = "COMPLETED"
        task.completed_at = datetime.now(tz=timezone.utc)
        if body.response is not None:
            task.response = body.response
        await _audit(
            session,
            actor=body.actor_user_id,
            roles=roles,
            action="task-completed",
            task=task,
        )
        await session.commit()
    return {"task_id": task_id, "state": task.state}


@router.post(
    "/{task_id}/decline",
    status_code=200,
    dependencies=[Depends(verify_internal_secret)],
)
async def decline_task(
    task_id: str,
    body: DeclineRequest,
    roles: frozenset[str] = Depends(requires_authenticated_persona),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    task = await _load_task_for_actor(session, task_id, body.actor_user_id, roles)
    if task.state not in ("COMPLETED", "DECLINED"):
        task.state = "DECLINED"
        task.declined_at = datetime.now(tz=timezone.utc)
        task.response = body.rationale
        await _audit(
            session,
            actor=body.actor_user_id,
            roles=roles,
            action="task-declined",
            task=task,
            rationale=body.rationale,
        )
        await session.commit()
    return {"task_id": task_id, "state": task.state}
