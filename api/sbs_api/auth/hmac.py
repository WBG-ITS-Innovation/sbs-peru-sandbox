# SPDX-License-Identifier: Apache-2.0
"""HMAC SHA-256 request-signing primitives per ADR 0027 amendment.

Six lines of canonical request:

    <METHOD-UPPERCASE>\\n
    <request-target-as-on-the-wire>\\n
    <lowercased-host-header>\\n
    <X-SBS-Timestamp-value>\\n
    <lowercase-hex(sha256(body))>\\n
    <institution_id>

Signature header is ``X-SBS-Signature: hmac-sha256-v1=<base64>``. The
algorithm prefix supports rotation without breaking clients.

Constant-time comparison via :func:`hmac.compare_digest` is enforced on
the verification path.
"""

from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

EMPTY_BODY_SHA256 = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # pragma: allowlist secret
)
SUPPORTED_ALGORITHMS = ("hmac-sha256-v1",)


@dataclass(frozen=True)
class CanonicalRequest:
    method: str
    target: str
    host: str
    timestamp: str
    body_sha256_hex: str
    institution_id: str

    def serialize(self) -> bytes:
        return "\n".join(
            (
                self.method,
                self.target,
                self.host,
                self.timestamp,
                self.body_sha256_hex,
                self.institution_id,
            )
        ).encode("utf-8")


def body_sha256_hex(body: bytes) -> str:
    """Return the lowercase hex SHA-256 of the request body.

    Empty body returns the constant
    ``e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855``
    (SHA-256 of the empty octet stream).
    """

    if not body:
        return EMPTY_BODY_SHA256
    return hashlib.sha256(body).hexdigest()


def build_canonical_request(
    *,
    method: str,
    target: str,
    host: str,
    timestamp: str,
    body: bytes,
    institution_id: str,
) -> CanonicalRequest:
    return CanonicalRequest(
        method=method.upper(),
        target=target,
        host=host.lower(),
        timestamp=timestamp,
        body_sha256_hex=body_sha256_hex(body),
        institution_id=institution_id,
    )


def compute_signature(secret: bytes, canonical: CanonicalRequest) -> str:
    """Return ``base64(HMAC-SHA256(secret, canonical))``."""

    mac = _hmac.new(secret, canonical.serialize(), hashlib.sha256).digest()
    return base64.b64encode(mac).decode("ascii")


def verify_signature(
    secret: bytes, canonical: CanonicalRequest, presented_b64: str
) -> bool:
    """Constant-time compare of ``presented_b64`` against the expected signature.

    Returns ``True`` if the signature is valid, ``False`` otherwise. The
    caller is responsible for raising the appropriate exception.
    """

    expected = compute_signature(secret, canonical)
    # ``hmac.compare_digest`` is the documented constant-time primitive.
    return _hmac.compare_digest(expected, presented_b64)


def parse_signature_header(header_value: str) -> str:
    """Return the base64 signature from ``hmac-sha256-v1=<base64>``.

    Raises ``ValueError`` if the algorithm prefix is unsupported or the
    structure is malformed.
    """

    if "=" not in header_value:
        raise ValueError("missing algorithm-prefix '=' separator")
    # The signature itself is base64 (which contains '=' padding), so we
    # split on the first '=' only.
    algorithm, _, sig = header_value.partition("=")
    algorithm = algorithm.strip()
    if algorithm not in SUPPORTED_ALGORITHMS:
        raise ValueError(f"unsupported algorithm prefix: {algorithm!r}")
    sig = sig.strip()
    if not sig:
        raise ValueError("signature value is empty")
    return sig


@dataclass(frozen=True)
class TimestampVerdict:
    """Result of timestamp validation. ``reason`` set only on failure."""

    valid: bool
    reason: str | None = None


def validate_timestamp(
    timestamp_str: str,
    *,
    now: datetime,
    skew_seconds: int,
    future_skew_max_seconds: int = 60,
) -> TimestampVerdict:
    """Check ``X-SBS-Timestamp`` against ``now`` per the ADR 0027 amendment.

    Past-tolerance: ``skew_seconds`` (default 300). Future-tolerance:
    ``future_skew_max_seconds`` (default 60). The asymmetry reflects
    that legitimate clock drift is overwhelmingly past-leaning and
    future-dated timestamps are an attack signature.
    """

    try:
        # RFC 3339 with explicit Z. ``fromisoformat`` accepts +00:00 and Z
        # since Python 3.11.
        parsed = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except ValueError:
        return TimestampVerdict(False, "timestamp is not RFC 3339")

    if parsed.tzinfo is None:
        return TimestampVerdict(False, "timestamp is missing the UTC timezone")
    parsed = parsed.astimezone(timezone.utc)

    delta = (now - parsed).total_seconds()  # positive if timestamp is past
    if delta > skew_seconds:
        return TimestampVerdict(
            False,
            f"timestamp is {delta:.0f}s in the past (max {skew_seconds}s)",
        )
    if delta < -future_skew_max_seconds:
        return TimestampVerdict(
            False,
            f"timestamp is {-delta:.0f}s in the future (max {future_skew_max_seconds}s)",
        )
    return TimestampVerdict(True)


def replay_cache_key(institution_id: str, signature_b64: str) -> str:
    """Return the Redis key used for replay protection.

    Truncates ``sha256(signature)`` to 16 hex chars (64 bits) for cache
    compactness; 64-bit collision space is overkill given the per-
    institution scoping.
    """

    digest = hashlib.sha256(signature_b64.encode("ascii")).hexdigest()[:16]
    return f"sbs:hmac:replay:{institution_id}:{digest}"
