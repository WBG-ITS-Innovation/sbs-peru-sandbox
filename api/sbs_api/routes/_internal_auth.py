# SPDX-License-Identifier: Apache-2.0
"""Shared internal-API authentication + role-scoping dependencies.

The shared-secret model gates server-to-server access (ADR 0040 §D8's
audit endpoint pattern); the role check applies on top per ADR 0040
§D7. The Next.js server reads the active persona's roles from the
session and forwards them as a comma-separated ``X-SBS-Role`` header
on every internal call. ADR 0043 (WS7) lifts the per-topic / per-
endpoint role-scope table to a declarative form; today the role
check sits inline in each route handler.
"""

from __future__ import annotations

import secrets
from typing import Iterable

from fastapi import Depends, Header, HTTPException

from sbs_api.config import Settings, get_settings


def verify_internal_secret(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    expected = settings.internal_api_secret
    if not expected:
        raise HTTPException(status_code=404, detail="Not Found")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    presented = authorization[len("Bearer ") :]
    if not secrets.compare_digest(presented, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


def parse_roles_header(header_value: str | None) -> frozenset[str]:
    """Parse the comma-separated X-SBS-Role header into a set."""

    if not header_value:
        return frozenset()
    return frozenset(part.strip() for part in header_value.split(",") if part.strip())


def require_any_role(allowed: Iterable[str]):
    """Build a dependency that 403s when none of ``allowed`` are present."""

    allowed_set = frozenset(allowed)

    def _checker(
        x_sbs_role: str | None = Header(default=None, alias="X-SBS-Role"),
    ) -> frozenset[str]:
        granted = parse_roles_header(x_sbs_role)
        if granted.isdisjoint(allowed_set):
            raise HTTPException(status_code=403, detail="Forbidden")
        return granted

    return _checker


def current_roles(
    x_sbs_role: str | None = Header(default=None, alias="X-SBS-Role"),
) -> frozenset[str]:
    """Dependency that returns the caller's granted roles without enforcing.

    Endpoints that adapt their response per role (institution-filtered
    for supervisor, unfiltered for analyst + head) use this and apply
    the filter themselves.
    """

    return parse_roles_header(x_sbs_role)
