"""GET /v1/internal/cockpit — supervisor-UI hero data (Prompt 10 / WS3).

Returns the initial-render snapshot the Next.js server component
fetches; subsequent updates arrive via the SSE stream at
``/v1/internal/sse/cockpit``. Same shared-secret authentication as
``/v1/internal/audit``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.cockpit import build_cockpit_snapshot
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
