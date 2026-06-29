# SPDX-License-Identifier: Apache-2.0
"""Webhook signature verification helper for the SBS SupTech API.

Pure Python standard library — no external dependencies. The helper
uses ``hmac``, ``hashlib``, and ``secrets`` from the standard library;
``hmac.compare_digest`` provides the constant-time comparison that
prevents timing-oracle attacks against the signature check.

Per [ADR 0038](../../docs/adr/0038-sdk-helper-scope-and-distribution.md)
this helper is intentionally tiny. It does NOT generate API clients,
handle OAuth tokens, or implement mTLS. It verifies the
``X-SBS-Signature`` header attached to outbound webhook callbacks
against the per-institution shared secret SBS distributed at
onboarding.

The canonical request shape mirrors the server-side outbound signer
in [api/sbs_api/webhook/signing.py](../../api/sbs_api/webhook/signing.py).
See [ADR 0035](../../docs/adr/0035-outbound-webhook-signing-contract.md)
for the contract.

Usage::

    from sbs_webhooks import (
        SignatureExpiredError,
        SignatureInvalidError,
        verify_signature,
    )

    # Inside your webhook receiver:
    try:
        verify_signature(
            secret=YOUR_OUTBOUND_SECRET_BYTES,
            key_id=request.headers["X-SBS-Key-Id"],
            timestamp=request.headers["X-SBS-Timestamp"],
            raw_body=request.body,        # bytes, exact bytes received
            signature_header=request.headers["X-SBS-Signature"],
            method=request.method,        # "POST"
            callback_path=request.path,   # "/sbs-callback"
            institution_id=YOUR_INSTITUTION_ID,
        )
    except SignatureExpiredError:
        # Reject — clock skew or replay window exceeded.
        return Response(status=401)
    except SignatureInvalidError:
        # Reject — signature did not match.
        return Response(status=401)
    # Signature good. Process the payload.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timezone

__all__ = [
    "ALGORITHM_PREFIX",
    "KEY_ID_SANDBOX_V1",
    "MAX_CLOCK_SKEW_SECONDS",
    "KeyIdUnknownError",
    "SignatureExpiredError",
    "SignatureInvalidError",
    "WebhookVerificationError",
    "canonicalize_request",
    "compute_signature",
    "constant_time_compare",
    "verify_signature",
]

# ---- Constants (mirror api/sbs_api/webhook/signing.py) -----------------------

ALGORITHM_PREFIX = "hmac-sha256-v1="
"""Algorithm prefix on the ``X-SBS-Signature`` header value."""

KEY_ID_SANDBOX_V1 = "sandbox-v1"
"""The ``X-SBS-Key-Id`` value used in the v0.1 sandbox."""

MAX_CLOCK_SKEW_SECONDS = 300
"""Clock-skew tolerance in seconds (5 minutes either direction).

Matches the server-side inbound timestamp window. A timestamp
older or newer than this is rejected as expired.
"""

# Cached SHA-256 of an empty bytes object, so callers that verify
# against an empty body don't re-hash on every call.
_EMPTY_BODY_SHA256 = hashlib.sha256(b"").hexdigest()


# ---- Exception hierarchy -----------------------------------------------------


class WebhookVerificationError(Exception):
    """Base class for verification failures."""


class SignatureInvalidError(WebhookVerificationError):
    """The signature did not match the expected HMAC."""


class SignatureExpiredError(WebhookVerificationError):
    """The timestamp is outside the clock-skew window."""


class KeyIdUnknownError(WebhookVerificationError):
    """The presented X-SBS-Key-Id is not one this helper knows.

    The v0.1 sandbox only accepts ``sandbox-v1``. Future rotation
    introduces new key ids; until then anything else is rejected.
    """


# ---- Public surface ----------------------------------------------------------


def constant_time_compare(a: bytes | str, b: bytes | str) -> bool:
    """Return True iff ``a`` and ``b`` are equal, in constant time.

    Thin wrapper over ``hmac.compare_digest``. Use this instead of
    ``==`` whenever comparing signature material — ``==`` can leak
    the position of the first differing byte through timing.
    """

    return hmac.compare_digest(a, b)


def canonicalize_request(
    *,
    method: str,
    callback_path: str,
    timestamp: str,
    raw_body: bytes,
    institution_id: str,
) -> bytes:
    """Build the five-line canonical request per ADR 0035.

    The lines are joined by ``\\n`` (LF, never CRLF) and UTF-8
    encoded.

    The five lines are:

    1. HTTP method, uppercased.
    2. Callback path-and-query (no scheme, no host).
    3. ``X-SBS-Timestamp`` value, verbatim.
    4. Lowercase hex SHA-256 of the raw body bytes.
    5. ``institution_id``.

    The host is intentionally NOT part of the canonical request —
    institutions verify against their own URL, which is the trust
    anchor (the URL was registered with SBS at onboarding).
    """

    body_hash = (
        _EMPTY_BODY_SHA256 if not raw_body else hashlib.sha256(raw_body).hexdigest()
    )
    return "\n".join(
        (
            method.upper(),
            callback_path,
            timestamp,
            body_hash,
            institution_id,
        )
    ).encode("utf-8")


def compute_signature(secret: bytes, canonical: bytes) -> str:
    """Return ``hmac-sha256-v1=<base64>`` over ``canonical``."""

    mac = hmac.new(secret, canonical, hashlib.sha256).digest()
    return ALGORITHM_PREFIX + base64.b64encode(mac).decode("ascii")


def _parse_timestamp(timestamp: str) -> datetime:
    """Parse an RFC 3339 / ISO 8601 UTC timestamp into an aware datetime.

    Accepts both the trailing ``Z`` form (``2026-05-20T12:34:56Z``)
    and the explicit ``+00:00`` form. Raises ``ValueError`` on
    anything else.
    """

    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    parsed = datetime.fromisoformat(timestamp)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware (UTC)")
    return parsed.astimezone(timezone.utc)


def verify_signature(
    *,
    secret: bytes,
    key_id: str,
    timestamp: str,
    raw_body: bytes,
    signature_header: str,
    method: str,
    callback_path: str,
    institution_id: str,
    now: datetime | None = None,
) -> None:
    """Verify an inbound SBS webhook callback signature.

    Raises ``SignatureExpiredError`` if the timestamp is outside the
    skew window; ``KeyIdUnknownError`` if the key_id is not one this
    helper recognises; ``SignatureInvalidError`` if the HMAC does not
    match the expected value. Returns ``None`` on success.

    ``now`` is overridable for tests; defaults to ``datetime.now(UTC)``.
    """

    if key_id != KEY_ID_SANDBOX_V1:
        raise KeyIdUnknownError(
            f"unknown X-SBS-Key-Id {key_id!r}; this helper expects "
            f"{KEY_ID_SANDBOX_V1!r}"
        )

    try:
        ts = _parse_timestamp(timestamp)
    except ValueError as exc:
        raise SignatureExpiredError(f"invalid timestamp: {exc}") from exc

    current = now if now is not None else datetime.now(timezone.utc)
    delta = abs((current - ts).total_seconds())
    if delta > MAX_CLOCK_SKEW_SECONDS:
        raise SignatureExpiredError(
            f"timestamp {timestamp} is {int(delta)}s from current time; "
            f"max skew is {MAX_CLOCK_SKEW_SECONDS}s"
        )

    if not signature_header.startswith(ALGORITHM_PREFIX):
        raise SignatureInvalidError(
            f"signature header must start with {ALGORITHM_PREFIX!r}"
        )

    canonical = canonicalize_request(
        method=method,
        callback_path=callback_path,
        timestamp=timestamp,
        raw_body=raw_body,
        institution_id=institution_id,
    )
    expected = compute_signature(secret, canonical)

    if not constant_time_compare(expected, signature_header):
        raise SignatureInvalidError("signature mismatch")
