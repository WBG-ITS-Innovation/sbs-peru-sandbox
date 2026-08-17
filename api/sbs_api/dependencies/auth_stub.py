# SPDX-License-Identifier: Apache-2.0
"""Dev-only persona auth stub (P-RESHAPE-8.6).

A testing affordance so local demo rehearsal can exercise persona
scoping without standing up Keycloak. Accepts a deliberately
non-standard token shape::

    Authorization: Bearer stub:<persona_id>

where ``persona_id`` ∈ {analyst, supervisor, head, superintendent, itops}. The token
resolves to a :class:`StubPrincipal` carrying the persona's role + the
exact scope set that role holds in :mod:`sbs_api.auth.persona_scopes`.

CRITICAL: stub auth is GATED ON BOTH ``auth_stub_enabled`` AND
``environment == 'dev'``. In any other configuration a ``stub:`` token
is ignored entirely and the real JWT / Keycloak path runs unchanged.
The non-standard ``stub:`` prefix makes its use obvious in logs and
code; every resolution emits a WARNING.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import HTTPException, Request

from sbs_api.auth.persona_scopes import (
    ROLE_ANALYST,
    ROLE_SBS_IT,
    ROLE_SUPERINTENDENT,
    ROLE_SUPERVISOR,
    ROLE_UNIT_HEAD,
    scopes_for_roles,
)
from sbs_api.config import Settings

log = logging.getLogger(__name__)

STUB_PREFIX = "stub:"

# Demo persona id → role string. analyst / supervisor / superintendent keep their names
# (archetypes, not real SBS individuals); head + itops are the current
# unit-head and IT personas in the registry.
STUB_PERSONA_ROLES: dict[str, str] = {
    "analyst": ROLE_ANALYST,
    "supervisor": ROLE_SUPERVISOR,
    "head": ROLE_UNIT_HEAD,
    "superintendent": ROLE_SUPERINTENDENT,
    "itops": ROLE_SBS_IT,
}


@dataclass(frozen=True)
class StubPrincipal:
    user_id: str
    username: str
    persona: str  # role string (conduct_analyst, … — a scope identifier)
    scopes: frozenset[str]
    roles: frozenset[str]


def stub_active(settings: Settings) -> bool:
    """Stub auth is honoured ONLY in dev with the flag on."""
    return bool(settings.auth_stub_enabled) and settings.environment == "dev"


def _parse_stub_persona(request: Request) -> str | None:
    """Return the persona id from a ``Bearer stub:<persona>`` header, or
    None when the header is absent or not a stub token."""
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    value = value.strip()
    if not value.startswith(STUB_PREFIX):
        return None
    return value[len(STUB_PREFIX):].strip()


def resolve_stub(request: Request, settings: Settings) -> StubPrincipal | None:
    """Resolve a stub principal, or None when stub auth is inactive or the
    request carries no ``stub:`` token. Raises 401 when stub auth IS active
    and the token names an unknown persona."""
    if not stub_active(settings):
        return None
    persona = _parse_stub_persona(request)
    if persona is None:
        return None  # real JWT / shared-secret path handles it
    role = STUB_PERSONA_ROLES.get(persona)
    if role is None:
        raise HTTPException(
            status_code=401,
            detail=f"Unknown stub persona '{persona}'. Expected one of "
            f"{sorted(STUB_PERSONA_ROLES)}.",
        )
    log.warning("STUB AUTH used (dev-only): persona=%s role=%s", persona, role)
    roles = frozenset({role})
    return StubPrincipal(
        user_id=f"stub-{persona}",
        username=persona,
        persona=role,
        scopes=scopes_for_roles(roles),
        roles=roles,
    )
