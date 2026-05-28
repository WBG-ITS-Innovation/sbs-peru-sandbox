"""Persona scope enforcement + data-filter helpers (P-RESHAPE-5).

``requires_scope(scope)`` is a FastAPI dependency factory: it reads the
caller's roles from the ``X-SBS-Role`` header, expands them to scopes
via :mod:`sbs_api.auth.persona_scopes`, and 403s (audited) when the
required scope is absent. It composes with the existing
``verify_internal_secret`` server-to-server gate.

``enforce_persona_data_filter`` is the second line of defence: even
when a persona holds a read scope, its *data shape* is constrained.
The Superintendent may read patterns but only as aggregates; SBS IT
may read ops telemetry but never a business field. The helpers here
let route handlers assert the persona-appropriate shape and strip
disallowed fields.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from fastapi import Depends, Header, HTTPException, Request

from sbs_api.auth.persona_scopes import (
    ALL_SCOPES,
    ROLE_SBS_IT,
    ROLE_SUPERINTENDENT,
    scopes_for_roles,
)

log = logging.getLogger(__name__)


def parse_roles_header(header_value: str | None) -> frozenset[str]:
    """Parse the comma-separated ``X-SBS-Role`` header into a set.

    Inlined here (rather than imported from ``routes._internal_auth``)
    to avoid a circular import: the routes package's ``__init__`` imports
    route modules that depend on this dependency.
    """
    if not header_value:
        return frozenset()
    return frozenset(part.strip() for part in header_value.split(",") if part.strip())


# Business fields that must NEVER appear in an SBS IT response. IT sees
# platform operations only — no business data of any kind.
BUSINESS_FIELDS: frozenset[str] = frozenset(
    {
        "complaint_id",
        "motivo_code",
        "complaint_category",
        "description_text",
        "narrative",
        "narrative_es",
        "narrative_en",
        "raw_narrative",
        "peer_risk_analysis",
        "pattern_summary_es",
        "pattern_summary_en",
        "peer_context_es",
        "peer_context_en",
        "contributing_complaint_ids",
        "ack_payload",
    }
)

# Fields forbidden on the Superintendent (exec) surface. Narrower than
# BUSINESS_FIELDS: the exec MAY see aggregate category counts and the
# pattern-level plain-language summary, but never a per-complaint
# identifier or any raw complaint narrative.
EXEC_FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "complaint_id",
        "description_text",
        "raw_narrative",
        "narrative",  # raw complaint narrative (PRR peer-narratives use *_es/_en)
        "contributing_complaint_ids",
        "ack_payload",
    }
)


def current_roles(
    x_sbs_role: str | None = Header(default=None, alias="X-SBS-Role"),
) -> frozenset[str]:
    return parse_roles_header(x_sbs_role)


def _roles_from_request(request: Request, x_sbs_role: str | None) -> frozenset[str]:
    """Resolve the caller's roles. In dev with the auth stub enabled a
    ``Bearer stub:<persona>`` token supplies the roles; otherwise the
    BFF-forwarded ``X-SBS-Role`` header does."""
    from sbs_api.config import get_settings
    from sbs_api.dependencies.auth_stub import resolve_stub

    principal = resolve_stub(request, get_settings())
    if principal is not None:
        return principal.roles
    return parse_roles_header(x_sbs_role)


def requires_scope(scope: str):
    """Dependency factory: 403 (audited) unless the caller's roles grant
    ``scope``."""

    def _checker(
        request: Request,
        x_sbs_role: str | None = Header(default=None, alias="X-SBS-Role"),
    ) -> frozenset[str]:
        roles = _roles_from_request(request, x_sbs_role)
        granted = scopes_for_roles(roles)
        if scope not in granted:
            # Audit the denial. We log rather than persist here to avoid a
            # DB dependency on the hot auth path; the persona_audit table
            # captures *attempted actions* that reach a handler.
            log.warning(
                "scope_denied scope=%s roles=%s",
                scope,
                sorted(roles),
            )
            raise HTTPException(status_code=403, detail="Forbidden")
        return roles

    return _checker


def requires_any_scope(*scopes: str):
    """Dependency factory: 403 (audited) unless the caller holds at least
    one of ``scopes``. Used by surfaces (e.g. the assignment inbox) that
    several personas legitimately reach."""

    needed = frozenset(scopes)

    def _checker(
        request: Request,
        x_sbs_role: str | None = Header(default=None, alias="X-SBS-Role"),
    ) -> frozenset[str]:
        roles = _roles_from_request(request, x_sbs_role)
        if scopes_for_roles(roles).isdisjoint(needed):
            log.warning(
                "scope_denied any_of=%s roles=%s", sorted(needed), sorted(roles)
            )
            raise HTTPException(status_code=403, detail="Forbidden")
        return roles

    return _checker


# "Any authenticated persona" gate (P-RESHAPE-8.5). 403s only when the
# caller holds no recognised persona scope at all — i.e. not one of the
# five personas. Built on requires_any_scope so the route-scope ratchet
# recognises it as a protected route.
requires_authenticated_persona = requires_any_scope(*sorted(ALL_SCOPES))


def is_aggregate_only(roles: frozenset[str]) -> bool:
    """True for personas that may only ever see aggregates (Superintendent)."""
    return ROLE_SUPERINTENDENT in roles and not (
        roles - {ROLE_SUPERINTENDENT}
    )


def is_ops_only(roles: frozenset[str]) -> bool:
    """True for the SBS IT persona when it holds no business-read role."""
    return ROLE_SBS_IT in roles and not (roles - {ROLE_SBS_IT})


def assert_no_business_fields(payload: Any) -> None:
    """Recursively assert no BUSINESS_FIELDS key appears in ``payload``.

    Used by ops/exec handlers as a self-check before returning, and by
    the PII-sentinel tests. Raises :class:`AssertionError` on a leak so a
    regression fails loudly in CI rather than silently shipping PII to
    the wrong persona.
    """
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k in BUSINESS_FIELDS:
                raise AssertionError(
                    f"business field {k!r} present in a restricted-persona payload"
                )
            assert_no_business_fields(v)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            assert_no_business_fields(item)


def assert_no_per_complaint_or_narrative(payload: Any) -> None:
    """Exec-surface sentinel: no per-complaint identifier or raw
    narrative may appear in a Superintendent payload. Aggregate category
    counts and pattern-level summaries are allowed."""
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k in EXEC_FORBIDDEN_FIELDS:
                raise AssertionError(
                    f"exec-forbidden field {k!r} present in a Superintendent payload"
                )
            assert_no_per_complaint_or_narrative(v)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            assert_no_per_complaint_or_narrative(item)


def strip_business_fields(payload: Any) -> Any:
    """Return a copy of ``payload`` with every BUSINESS_FIELDS key removed
    (recursively). Defensive belt-and-braces for shared serialisers."""
    if isinstance(payload, dict):
        return {
            k: strip_business_fields(v)
            for k, v in payload.items()
            if k not in BUSINESS_FIELDS
        }
    if isinstance(payload, list):
        return [strip_business_fields(v) for v in payload]
    return payload


def enforce_persona_data_filter(
    roles: frozenset[str], payload: Any, *, restricted_when: Iterable[str] = ()
) -> Any:
    """Strip business fields for restricted personas.

    ``restricted_when`` lists roles for which the payload must be
    business-field-free (defaults to Superintendent + SBS IT). For any
    other persona the payload passes through unchanged.
    """
    restricted = set(restricted_when) or {ROLE_SUPERINTENDENT, ROLE_SBS_IT}
    if roles & restricted:
        return strip_business_fields(payload)
    return payload
