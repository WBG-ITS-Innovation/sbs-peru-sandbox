"""Audit-event recording — the single entrypoint for the cross-screen audit chain.

Every screen that mutates state writes through :func:`record_audit_event`.
The audit screen (WS6) reads from a single table; if any screen invents
its own audit-writing path, the audit screen will show some actions and
not others. Routing through this module is the contract.

Usage from a route handler::

    from sbs_api.audit import record_audit_event

    await record_audit_event(
        session,
        actor_type="user",
        actor_id="maria@sbs.gob.pe",
        action="switch-persona",
        object_type="session",
        object_id=session_id,
        meta={"from": "maria@sbs.gob.pe", "to": "lucia@sbs.gob.pe"},
    )
    await session.commit()

The caller commits. The function does not flush implicitly so the audit
row participates in the caller's transaction — partial state plus an
audit row of "it happened" must never land.
"""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.audit_event import AuditEvent

ActorType = Literal["user", "agent"]


async def record_audit_event(
    session: AsyncSession,
    *,
    actor_type: ActorType,
    actor_id: str,
    action: str,
    object_type: str,
    object_id: str,
    diff: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append an audit row to the caller's session.

    The caller commits. The row's ``created_at`` is server-assigned;
    ``id`` is server-assigned (BigInteger autoincrement). Callers that
    need the assigned ``id`` should call ``await session.flush()`` after.

    The kebab-case shape of ``action`` is enforced by a check constraint
    in Postgres; passing a non-kebab string raises ``IntegrityError`` at
    commit time, not at this call site.
    """

    if actor_type not in ("user", "agent"):
        raise ValueError(
            f"actor_type must be 'user' or 'agent', got {actor_type!r}"
        )

    event = AuditEvent(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        diff=diff,
        meta=meta,
    )
    session.add(event)
    return event
