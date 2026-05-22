"""GET /v1/internal/audit — paginated audit-log read endpoint.

Reads from ``audit_events`` (the cross-screen audit chain). Returns
50 rows per page by default; the WS0 seed cap is 80 so two pages
exercise the pagination on the demo path. Role-gated to the three
conduct scopes per ADR 0040 §D7 (audit is the governance signal —
everyone with conduct access reads it).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.audit_event import AuditEvent
from sbs_api.dependencies.db import get_session
from sbs_api.routes._internal_auth import require_any_role, verify_internal_secret

router = APIRouter(prefix="/internal", tags=["Internal"])

_CONDUCT_SCOPES = require_any_role(
    {"sbs:conduct:supervisor", "sbs:conduct:analyst", "sbs:conduct:head"}
)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


@router.get(
    "/audit",
    dependencies=[Depends(verify_internal_secret), Depends(_CONDUCT_SCOPES)],
)
async def get_audit(
    actor_type: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    object_type: str | None = Query(default=None),
    object_id: str | None = Query(default=None),
    from_created_at: datetime | None = Query(default=None),
    to_created_at: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1, le=1000),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    base = select(AuditEvent)
    if actor_type:
        base = base.where(AuditEvent.actor_type == actor_type)
    if actor_id:
        base = base.where(AuditEvent.actor_id == actor_id)
    if action:
        base = base.where(AuditEvent.action == action)
    if object_type:
        base = base.where(AuditEvent.object_type == object_type)
    if object_id:
        base = base.where(AuditEvent.object_id == object_id)
    if from_created_at:
        base = base.where(AuditEvent.created_at >= from_created_at)
    if to_created_at:
        base = base.where(AuditEvent.created_at <= to_created_at)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    rows_q = (
        base.order_by(desc(AuditEvent.created_at))
        .offset(offset)
        .limit(page_size)
    )
    rows = (await session.execute(rows_q)).scalars().all()

    items = [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat(timespec="seconds"),
            "actor_type": r.actor_type,
            "actor_id": r.actor_id,
            "action": r.action,
            "object_type": r.object_type,
            "object_id": r.object_id,
            "diff": r.diff,
            "meta": r.meta,
        }
        for r in rows
    ]

    return {
        "items": items,
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "total_pages": (int(total) + page_size - 1) // page_size if total else 0,
    }
