# SPDX-License-Identifier: Apache-2.0
"""OAuth scope-enforcing dependency factory — ADR 0032.

Use as:

    from sbs_api.dependencies.oauth import verified_oauth_token_with_scope
    from sbs_api.auth.scopes import COMPLAINTS_WRITE

    @router.post("/v1/complaints")
    async def create_complaint(
        token = Depends(verified_oauth_token_with_scope(COMPLAINTS_WRITE)),
    ):
        ...

The dependency:
1. Reads ``Authorization: Bearer <jwt>`` header.
2. Verifies signature, exp, iss, aud, and required claims.
3. Recomputes the ``cnf.x5t#S256`` claim against the current mTLS
   subject's cert thumbprint — closes the cert-binding loop per
   RFC 8705 §3.1.
4. Enforces that *all* required scopes are present in the granted set.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request

from sbs_api.config import get_settings
from sbs_api.dependencies.auth_stub import resolve_stub

from sbs_api.auth.oauth import (
    TokenClaims,
    TokenVerificationError,
    load_or_create_signing_key,
    verify_token,
)
from sbs_api.dependencies.mtls import MtlsSubject, verified_mtls_subject
from sbs_api.errors.exceptions import (
    TokenCertThumbprintMismatch,
    TokenExpired,
    TokenInvalid,
    TokenRequired,
    TokenScopeInsufficient,
)


# ---------------------------------------------------------------------------
# Signing-key management (sandbox-grade — see ADR 0032 §Consequences)
# ---------------------------------------------------------------------------

_signing_key: bytes | None = None


def get_signing_key() -> bytes:
    global _signing_key
    if _signing_key is None:
        _signing_key = load_or_create_signing_key()
    return _signing_key


def override_signing_key_for_test(key: bytes) -> None:
    global _signing_key
    _signing_key = key


def reset_signing_key_for_test() -> None:
    global _signing_key
    _signing_key = None


# ---------------------------------------------------------------------------
# Dependency factory
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifiedToken:
    """The verified token payload + the mTLS subject it's bound to."""

    institution_id: str
    granted_scopes: frozenset[str]
    cert_thumbprint: str


def _extract_bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if not header:
        raise TokenRequired(detail="Missing Authorization header.")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value:
        raise TokenRequired(
            detail="Authorization header must be 'Bearer <token>'."
        )
    return value.strip()


# Cache scope-set → dependency closures so the same call returns the
# same function reference, which is what FastAPI's
# ``app.dependency_overrides`` keys on. Without this, tests cannot
# override the scope dep because each ``verified_oauth_token_with_scope("foo")``
# call would build a fresh closure with a different identity.
_dep_cache: dict[frozenset[str], "object"] = {}


def verified_oauth_token_with_scope(*required_scopes: str):
    """Return a FastAPI dependency that enforces the given scopes.

    Cached by scope-set so test ``dependency_overrides`` can target the
    closure produced by ``verified_oauth_token_with_scope(SCOPE)``.
    """

    required = frozenset(required_scopes)
    cached = _dep_cache.get(required)
    if cached is not None:
        return cached

    async def dependency(
        request: Request,
        mtls_subject: MtlsSubject = Depends(verified_mtls_subject),
    ) -> VerifiedToken:
        # Dev-only persona stub (P-RESHAPE-8.6): honoured only when
        # auth_stub_enabled AND environment == "dev"; see auth_stub.py.
        principal = resolve_stub(request, get_settings())
        if principal is not None:
            missing_stub = required - principal.scopes
            if missing_stub:
                raise TokenScopeInsufficient(
                    detail=(
                        f"Persona '{principal.username}' is missing required "
                        f"scope(s): {sorted(missing_stub)}."
                    )
                )
            return VerifiedToken(
                institution_id=f"stub-{principal.username}",
                granted_scopes=principal.scopes,
                cert_thumbprint="0" * 64,
            )

        token_str = _extract_bearer(request)
        try:
            claims: TokenClaims = verify_token(token_str, key=get_signing_key())
        except TokenVerificationError as exc:
            if exc.expired:
                raise TokenExpired(detail=exc.reason) from exc
            raise TokenInvalid(detail=exc.reason) from exc

        if claims.cert_thumbprint_sha256_hex.lower() != mtls_subject.cert_thumbprint.lower():
            raise TokenCertThumbprintMismatch(
                detail=(
                    "Token's cnf.x5t#S256 thumbprint does not match the "
                    "presenting client certificate. RFC 8705 §3.1 binding "
                    "rejects the token."
                )
            )

        if claims.institution_id != mtls_subject.institution_id:
            # This is a subtle attack class — a token issued for institution
            # X presented over institution X's cert *but reused* through a
            # mTLS connection where X's cert has been re-bound to a
            # different institution_id row. The thumbprint check above
            # closes the standard case; this catches the database-side
            # drift case.
            raise TokenCertThumbprintMismatch(
                detail="Token sub does not match the mTLS-resolved institution_id."
            )

        missing = required - claims.granted_scopes
        if missing:
            raise TokenScopeInsufficient(
                detail=(
                    f"Token is missing required scope(s): {sorted(missing)}. "
                    f"Granted scopes: {sorted(claims.granted_scopes)}."
                )
            )

        return VerifiedToken(
            institution_id=claims.institution_id,
            granted_scopes=claims.granted_scopes,
            cert_thumbprint=claims.cert_thumbprint_sha256_hex,
        )

    _dep_cache[required] = dependency
    return dependency
