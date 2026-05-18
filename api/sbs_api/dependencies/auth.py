"""Tenancy-binding dependency — stub until Prompt 7.

Behaviour gated on :data:`Settings.auth_stub_enabled`:

* ``True``  — returns a fixed :class:`AuthContext` representing the demo
              institution. Local-dev convenience only.
* ``False`` — raises :class:`AuthenticationNotConfigured` with stable code
              ``AUTH_NOT_CONFIGURED`` so the runtime fails closed when real
              auth isn't wired. This is the foot-gun mitigation; production
              never starts without real authentication wired.

The route handler validates that the caller's ``institution_id`` matches
the value carried in the request body. The validation lives in the route
handler because it varies (POST has body.institution_id, GET has path or
query param).
"""

from __future__ import annotations

from dataclasses import dataclass

from sbs_api.config import get_settings
from sbs_api.errors.exceptions import AuthenticationNotConfigured


@dataclass(frozen=True)
class AuthContext:
    institution_id: str
    scopes: frozenset[str]

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def get_auth_context() -> AuthContext:
    """Return the authenticated caller, or fail closed.

    Returned by FastAPI as a dependency. Tests can override via
    ``app.dependency_overrides[get_auth_context]``.
    """

    settings = get_settings()
    if not settings.auth_stub_enabled:
        raise AuthenticationNotConfigured(
            detail=(
                "Authentication is not configured. Set AUTH_STUB_ENABLED=true "
                "for local development, or deploy a build with real auth wired "
                "(Prompt 7+)."
            )
        )
    return AuthContext(
        institution_id=settings.auth_stub_institution_id,
        scopes=frozenset(
            {
                "complaints.read",
                "complaints.write",
                "batches.read",
                "batches.write",
            }
        ),
    )
