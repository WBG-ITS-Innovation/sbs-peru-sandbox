"""POST /v1/internal/ops/incidents — SBS IT annotates an incident (P-RESHAPE-8.5).

Rosa's one write action. Ops-only: the request and response carry NO
business field (asserted before returning). Remediation actions (retry,
requeue, circuit-break) are deferred to P-RESHAPE-9.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.auth.persona_scopes import INCIDENT_ANNOTATE, primary_persona
from sbs_api.db.models.incident_annotation import IncidentAnnotation
from sbs_api.db.models.persona_audit import PersonaAudit
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.persona import assert_no_business_fields, requires_scope
from sbs_api.routes._internal_auth import verify_internal_secret

router = APIRouter(prefix="/internal/ops", tags=["Ops"])

_ANNOTATE = requires_scope(INCIDENT_ANNOTATE)


class IncidentAnnotationRequest(BaseModel):
    actor_user_id: str = Field(min_length=1, max_length=128)
    note: str = Field(min_length=20, max_length=4_000)
    component: str | None = Field(default=None, max_length=64)
    severity: str | None = Field(default=None, max_length=16)


@router.post(
    "/incidents",
    status_code=201,
    dependencies=[Depends(verify_internal_secret)],
)
async def annotate_incident(
    body: IncidentAnnotationRequest,
    roles: frozenset[str] = Depends(_ANNOTATE),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    persona = primary_persona(roles) or "unknown"
    now = datetime.now(tz=timezone.utc)
    row = IncidentAnnotation(
        created_at=now,
        actor_user_id=body.actor_user_id,
        component=body.component,
        severity=body.severity,
        note=body.note,
    )
    session.add(row)
    session.add(
        PersonaAudit(
            actor_user_id=body.actor_user_id,
            persona=persona,
            action="incident-annotated",
            target_type="INCIDENT",
            target_id=body.component,
            params={"severity": body.severity},
        )
    )
    await session.flush()
    payload = {
        "id": row.id,
        "component": row.component,
        "severity": row.severity,
        "created_at": row.created_at.isoformat(timespec="seconds"),
    }
    assert_no_business_fields(payload)
    await session.commit()
    return payload
