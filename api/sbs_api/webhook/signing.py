"""Outbound webhook HMAC signing (ADR 0035 + ADR 0027 amendment §outbound).

Five-line canonical request:

    <METHOD-UPPERCASE>\\n
    <callback-path>\\n
    <X-SBS-Timestamp>\\n
    <lowercase-hex(sha256(body))>\\n
    <institution_id>

The Host header is **not** included for outbound — institutions verify
against their own URL, not a server-controlled Host. Inbound has Host
because the proxy can rewrite it; outbound is server-originated to
a known URL, so the URL itself is the trust anchor.

Headers attached to outbound HTTP requests:

* ``X-SBS-Timestamp``  — ISO-8601 UTC, e.g. ``2026-05-20T12:34:56Z``
* ``X-SBS-Signature``  — ``hmac-sha256-v1=<base64>``
* ``X-SBS-Key-Id``     — ``sandbox-v1`` for every row written by
                          Prompt 8 (the kid column on
                          ``outbound_webhook_secrets`` enables future
                          rotation; the rotation reader lands in
                          Part 8 admin).
"""

from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
from dataclasses import dataclass

KID_SANDBOX_V1 = "sandbox-v1"
ALGORITHM_PREFIX = "hmac-sha256-v1="
SUPPORTED_ALGORITHMS = ("hmac-sha256-v1",)

_EMPTY_BODY_SHA256 = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # pragma: allowlist secret
)


@dataclass(frozen=True)
class OutboundCanonicalRequest:
    method: str
    callback_path: str
    timestamp: str
    body_sha256_hex: str
    institution_id: str

    def serialize(self) -> bytes:
        return "\n".join(
            (
                self.method,
                self.callback_path,
                self.timestamp,
                self.body_sha256_hex,
                self.institution_id,
            )
        ).encode("utf-8")


def _body_sha256_hex(body: bytes) -> str:
    if not body:
        return _EMPTY_BODY_SHA256
    return hashlib.sha256(body).hexdigest()


def build_outbound_canonical_request(
    *,
    method: str,
    callback_path: str,
    timestamp: str,
    body: bytes,
    institution_id: str,
) -> OutboundCanonicalRequest:
    """Construct the five-line outbound canonical request.

    ``callback_path`` is the path-and-query of the URL, e.g.
    ``/sbs-callback?env=sandbox``. The host is not part of the
    canonical request (see module docstring rationale).
    """

    return OutboundCanonicalRequest(
        method=method.upper(),
        callback_path=callback_path,
        timestamp=timestamp,
        body_sha256_hex=_body_sha256_hex(body),
        institution_id=institution_id,
    )


def compute_outbound_signature(
    secret: bytes, canonical: OutboundCanonicalRequest
) -> str:
    """Return ``base64(HMAC-SHA256(secret, canonical))``."""

    mac = _hmac.new(secret, canonical.serialize(), hashlib.sha256).digest()
    return base64.b64encode(mac).decode("ascii")


def verify_outbound_signature(
    secret: bytes,
    canonical: OutboundCanonicalRequest,
    presented_b64: str,
) -> bool:
    """Constant-time compare of ``presented_b64`` against the expected sig."""

    expected = compute_outbound_signature(secret, canonical)
    return _hmac.compare_digest(expected, presented_b64)


def signature_header(b64: str) -> str:
    """Construct the ``X-SBS-Signature`` header value."""

    return f"{ALGORITHM_PREFIX}{b64}"


def parse_signature_header(header_value: str) -> str:
    """Strip the algorithm prefix; raise ``ValueError`` on unsupported algo."""

    for prefix in SUPPORTED_ALGORITHMS:
        full_prefix = f"{prefix}="
        if header_value.startswith(full_prefix):
            return header_value[len(full_prefix):]
    raise ValueError(
        f"unsupported signature algorithm; expected one of "
        f"{', '.join(SUPPORTED_ALGORITHMS)}"
    )
