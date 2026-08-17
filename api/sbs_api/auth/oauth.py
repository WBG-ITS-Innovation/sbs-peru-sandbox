# SPDX-License-Identifier: Apache-2.0
"""OAuth 2.0 client_credentials primitives per ADR 0032 (with pressure-test fixes).

Pure helpers: JWT issuance, JWT verification, client_secret hash/verify.
The dependency wiring is in :mod:`sbs_api.dependencies.oauth`; the
route handler is in :mod:`sbs_api.routes.oauth`.

Key contract points:

* Header: ``alg=HS256`` (sandbox), ``kid=sandbox-v1`` from issuance day
  one. The ``kid`` enables the HS256→RS256 migration in Part 9 and key
  rotation without breaking SDK consumers.
* Claims: ``iss``, ``aud``, ``iat``, ``exp``, ``sub`` (institution_id),
  ``scope`` (space-separated granted scopes), ``cnf.x5t#S256`` (RFC 8705
  cert-binding).
* Verifier rejects any ``alg`` other than the one configured for the
  deployment — closes the classical algorithm-confusion attack.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

SANDBOX_KEY_FILE = "dev-ca/oauth-signing-key.bin"
DEFAULT_TTL_SECONDS = 900  # 15 minutes per ADR 0032
DEFAULT_KID = "sandbox-v1"
DEFAULT_ISS = "https://sbs-suptech-sandbox.local"
DEFAULT_AUD = "sbs-api"
DEFAULT_ALG = "HS256"

_hasher = PasswordHasher()


# ---------------------------------------------------------------------------
# Signing key management
# ---------------------------------------------------------------------------


def load_or_create_signing_key(path: str = SANDBOX_KEY_FILE) -> bytes:
    """Return the HS256 signing key. Creates it on first use.

    Sandbox-only behaviour: a 32-byte random key persisted to disk
    means anyone with read access to the file can mint tokens for any
    institution. ADR 0032 acknowledges this and defers RS256 + KMS to
    Part 9.
    """

    p = Path(path)
    if p.exists():
        return p.read_bytes()
    p.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    p.write_bytes(key)
    p.chmod(0o600)
    return key


# ---------------------------------------------------------------------------
# Client secret hashing
# ---------------------------------------------------------------------------


def hash_client_secret(plain: str) -> str:
    """Return an Argon2id-encoded hash suitable for the oauth_clients table."""

    return _hasher.hash(plain)


def verify_client_secret(presented: str, stored_hash: str) -> bool:
    """Constant-time verify; returns False on mismatch or malformed hash."""

    try:
        return _hasher.verify(stored_hash, presented)
    except (VerifyMismatchError, InvalidHashError):
        return False


# ---------------------------------------------------------------------------
# JWT issuance + verification
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IssueOptions:
    institution_id: str
    granted_scopes: frozenset[str]
    cert_thumbprint_sha256_hex: str
    ttl_seconds: int = DEFAULT_TTL_SECONDS
    iss: str = DEFAULT_ISS
    aud: str = DEFAULT_AUD


def issue_token(
    options: IssueOptions,
    *,
    key: bytes,
    kid: str = DEFAULT_KID,
    alg: str = DEFAULT_ALG,
    now: datetime | None = None,
) -> str:
    """Return a signed JWT carrying the cert-binding confirmation claim."""

    now = now or datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "iss": options.iss,
        "aud": options.aud,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=options.ttl_seconds)).timestamp()),
        "sub": options.institution_id,
        "scope": " ".join(sorted(options.granted_scopes)),
        "cnf": {"x5t#S256": options.cert_thumbprint_sha256_hex},
    }
    return jwt.encode(payload, key, algorithm=alg, headers={"kid": kid})


@dataclass(frozen=True)
class TokenClaims:
    institution_id: str
    granted_scopes: frozenset[str]
    cert_thumbprint_sha256_hex: str
    exp: datetime


class TokenVerificationError(Exception):
    """Lifted into the SBSAPIException ladder by the dependency."""

    def __init__(self, reason: str, *, expired: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.expired = expired


def verify_token(
    token: str,
    *,
    key: bytes,
    expected_iss: str = DEFAULT_ISS,
    expected_aud: str = DEFAULT_AUD,
    accepted_algs: tuple[str, ...] = (DEFAULT_ALG,),
) -> TokenClaims:
    """Validate signature, structure, and required claims.

    Rejects any ``alg`` not in ``accepted_algs`` *before* signature
    verification — closes the classical algorithm-confusion attack.
    """

    try:
        decoded = jwt.decode(
            token,
            key,
            algorithms=list(accepted_algs),
            audience=expected_aud,
            issuer=expected_iss,
            options={"require": ["iss", "aud", "exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenVerificationError("token expired", expired=True) from exc
    except jwt.InvalidTokenError as exc:
        raise TokenVerificationError(f"token invalid: {exc}") from exc

    sub = decoded.get("sub")
    scope_str = decoded.get("scope", "")
    cnf = decoded.get("cnf") or {}
    thumbprint = cnf.get("x5t#S256")
    if not isinstance(sub, str) or not sub:
        raise TokenVerificationError("token missing 'sub' claim")
    if not isinstance(thumbprint, str) or not thumbprint:
        raise TokenVerificationError("token missing 'cnf.x5t#S256' claim")

    return TokenClaims(
        institution_id=sub,
        granted_scopes=frozenset(scope_str.split()) if scope_str else frozenset(),
        cert_thumbprint_sha256_hex=thumbprint,
        exp=datetime.fromtimestamp(decoded["exp"], tz=timezone.utc),
    )
