"""Institution operational status endpoint."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Path
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.auth.scopes import STATUS_READ
from sbs_api.config import get_settings
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.mtls import MtlsSubject
from sbs_api.dependencies.oauth import (
    VerifiedToken,
    verified_oauth_token_with_scope,
)
from sbs_api.dependencies.rate_limit import business_bucket
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.institution import InstitutionRecord
from sbs_api.errors.exceptions import ResourceNotFound
from sbs_api.models.responses import InstitutionStatus

router = APIRouter(tags=["Institutions"])


@router.get("/institutions/{institution_id}/status", response_model=InstitutionStatus)
async def get_institution_status(
    institution_id: str = Path(..., pattern=r"^SBS-\d{4,6}$"),
    token: VerifiedToken = Depends(verified_oauth_token_with_scope(STATUS_READ)),
    _rate_limit: MtlsSubject = Depends(business_bucket),
    session: AsyncSession = Depends(get_session),
) -> InstitutionStatus:
    if institution_id != token.institution_id:
        # Same posture as complaints: 404 not 403, do not leak existence.
        raise ResourceNotFound(detail=f"institution {institution_id!r} not found.")

    inst_result = await session.execute(
        select(InstitutionRecord).where(InstitutionRecord.institution_id == institution_id)
    )
    institution = inst_result.scalar_one_or_none()
    if institution is None:
        raise ResourceNotFound(detail=f"institution {institution_id!r} not found.")

    today = datetime.now(timezone.utc).date()
    count_result = await session.execute(
        select(func.count())
        .select_from(ComplaintRecord)
        .where(ComplaintRecord.institution_id == institution_id)
        .where(func.date(ComplaintRecord.received_at) == today)
    )
    count_today = int(count_result.scalar() or 0)

    last_result = await session.execute(
        select(func.max(ComplaintRecord.received_at)).where(
            ComplaintRecord.institution_id == institution_id
        )
    )
    last_at = last_result.scalar()

    # Resolve effective rate limit per ADR 0033: per-institution
    # override wins; otherwise the tier default applies. The DB column
    # is nullable (NULL = use tier default) after migration 0002 so the
    # response field cannot be sourced verbatim.
    settings = get_settings()
    effective_limit = institution.rate_limit_per_minute
    if effective_limit is None:
        if institution.tier_classification == "large":
            effective_limit = settings.rate_limit_tier_large_per_minute
        else:
            effective_limit = settings.rate_limit_tier_small_per_minute

    return InstitutionStatus(
        institution_id=institution_id,
        onboarded=institution.onboarded,
        rate_limit_per_minute=effective_limit,
        complaints_received_today=count_today,
        last_submission_at=last_at,
        schema_version=institution.schema_version,
    )
