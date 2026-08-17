# SPDX-License-Identifier: Apache-2.0
"""GET /v1/internal/cockpit — supervisor-UI hero data (Prompt 10 / WS3).

Returns the initial-render snapshot the Next.js server component
fetches; subsequent updates arrive via the SSE stream at
``/v1/internal/sse/cockpit``. Same shared-secret authentication as
``/v1/internal/audit``.

P11 demo-ui-polish overlay adds ``GET /v1/internal/cockpit/taxonomy-stats``
which the cockpit stat tile reads to show
"Taxonomy normalizations today: N across M institutions".
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.cockpit import build_cockpit_snapshot
from sbs_api.db.models.audit_event import AuditEvent
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.dependencies.db import get_session
from sbs_api.routes._internal_auth import verify_internal_secret

router = APIRouter(prefix="/internal", tags=["Internal"])


@router.get(
    "/cockpit",
    dependencies=[Depends(verify_internal_secret)],
)
async def get_cockpit(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await build_cockpit_snapshot(session)


class TaxonomyStatsResponse(BaseModel):
    """Counters for the cockpit's "Taxonomy harmonization today" tile."""

    normalizations_today: int = Field(
        ge=0,
        description=(
            "Number of taxonomy-normalized audit rows created since "
            "00:00 UTC today. One row per submission that had ≥1 field "
            "mapped to canonical."
        ),
    )
    institutions_affected: int = Field(
        ge=0,
        description=(
            "Distinct institutions whose submissions contributed to "
            "normalizations_today. Joined via complaints.institution_id."
        ),
    )
    as_of: str = Field(
        description="ISO 8601 timestamp at which these counters were computed."
    )


@router.get(
    "/cockpit/taxonomy-stats",
    response_model=TaxonomyStatsResponse,
    dependencies=[Depends(verify_internal_secret)],
)
async def get_taxonomy_stats(
    session: AsyncSession = Depends(get_session),
) -> TaxonomyStatsResponse:
    """Return the two counters the cockpit stat tile renders.

    Window: ``created_at >= 00:00 UTC today``. "Institutions affected"
    is the distinct count of ``complaints.institution_id`` joined on
    the taxonomy-normalized audit row's ``object_id`` (the complaint
    id) — institution prefix on the complaint id is not reliable
    because the COD_REC the institution sends becomes the canonical
    id pattern only for the seeded ``BCO-`` and ``COP-`` rows.
    """

    now = datetime.now(tz=timezone.utc)
    today_start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)

    normalizations_q = (
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.action == "taxonomy-normalized")
        .where(AuditEvent.created_at >= today_start)
    )
    normalizations_today = int(
        (await session.execute(normalizations_q)).scalar_one()
    )

    institutions_q = (
        select(func.count(distinct(ComplaintRecord.institution_id)))
        .select_from(AuditEvent)
        .join(
            ComplaintRecord,
            ComplaintRecord.complaint_id == AuditEvent.object_id,
        )
        .where(AuditEvent.action == "taxonomy-normalized")
        .where(AuditEvent.created_at >= today_start)
    )
    institutions_affected = int(
        (await session.execute(institutions_q)).scalar_one() or 0
    )

    return TaxonomyStatsResponse(
        normalizations_today=normalizations_today,
        institutions_affected=institutions_affected,
        as_of=now.isoformat(timespec="seconds"),
    )
