"""GET /v1/internal/cockpit/actions — the persona action surface (P-RESHAPE-8.5).

Returns the set of action verbs the caller's persona can invoke, so a
dashboard renders buttons rather than a wall of read-only data. The list
is filtered to the caller's roles from the locked action registry.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from sbs_api.dependencies.persona import requires_authenticated_persona
from sbs_api.personas.action_registry import actions_for_roles
from sbs_api.routes._internal_auth import verify_internal_secret

router = APIRouter(prefix="/internal/cockpit", tags=["Cockpit"])


@router.get(
    "/actions",
    dependencies=[Depends(verify_internal_secret)],
)
async def list_actions(
    roles: frozenset[str] = Depends(requires_authenticated_persona),
) -> dict[str, Any]:
    actions = actions_for_roles(roles)
    return {"actions": actions, "total": len(actions)}
