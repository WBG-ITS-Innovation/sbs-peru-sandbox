"""POST /v1/internal/findings/manual — analyst proposes a pattern (P-RESHAPE-8.5).

The Analyst's ``propose_pattern`` action. Persists a ``manual_findings``
row (kept out of the automated ``pattern_detections`` trigger path) and a
persona_audit row. Minimum viable: scope + 30-char rationale + persist.
Downstream triage of manual proposals is deferred.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.auth.persona_scopes import FINDINGS_PROPOSE, primary_persona
from sbs_api.db.models.manual_finding import ManualFinding
from sbs_api.db.models.persona_audit import PersonaAudit
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.persona import requires_scope
from sbs_api.routes._internal_auth import verify_internal_secret

router = APIRouter(prefix="/internal", tags=["Internal"])

_PROPOSE = requires_scope(FINDINGS_PROPOSE)


class ManualFindingRequest(BaseModel):
    proposed_by_user_id: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=2_000)
    rationale: str = Field(
        min_length=30,
        max_length=2_000,
        description="Why this proposal merits attention — >= 30 chars.",
    )
    institution_code: str | None = Field(default=None, max_length=32)


@router.post(
    "/findings/manual",
    status_code=201,
    dependencies=[Depends(verify_internal_secret)],
)
async def propose_pattern(
    body: ManualFindingRequest,
    roles: frozenset[str] = Depends(_PROPOSE),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    persona = primary_persona(roles) or "unknown"
    finding_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc)
    session.add(
        ManualFinding(
            finding_id=finding_id,
            created_at=now,
            proposed_by_user_id=body.proposed_by_user_id,
            persona=persona,
            institution_code=body.institution_code,
            summary=body.summary,
            rationale=body.rationale,
            status="PROPOSED",
        )
    )
    session.add(
        PersonaAudit(
            actor_user_id=body.proposed_by_user_id,
            persona=persona,
            action="pattern-proposed",
            target_type="MANUAL_FINDING",
            target_id=finding_id,
            rationale=body.rationale,
        )
    )
    await session.commit()
    return {
        "finding_id": finding_id,
        "status": "PROPOSED",
        "created_at": now.isoformat(timespec="seconds"),
    }
