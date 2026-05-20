"""Outbound webhook signing + delivery (ADR 0035).

The signing module mirrors the inbound HMAC canonical-request shape
(five lines: method / callback-path / timestamp / body-hash /
institution_id) using a per-institution outbound secret distinct from
the inbound HMAC secret. Header is ``X-SBS-Signature: hmac-sha256-v1=
<base64>`` plus ``X-SBS-Timestamp`` and ``X-SBS-Key-Id: sandbox-v1``.

The URL validation module enforces HTTPS-only / FQDN-only / public-IP
only. The single env var ``SBS_API_ALLOW_INSECURE_WEBHOOK_URLS=true``
bypasses all three checks; the application refuses to boot when this
is set with ``environment in {staging, prod}``.

The delivery module composes both with httpx for the actual HTTP call;
retries follow ADR 0035's Stripe-shaped backoff (30s, 2min, 10min,
1hr, 6hr).
"""

from sbs_api.webhook.signing import (
    KID_SANDBOX_V1,
    OutboundCanonicalRequest,
    build_outbound_canonical_request,
    compute_outbound_signature,
    verify_outbound_signature,
)
from sbs_api.webhook.url_validation import (
    WebhookUrlValidationResult,
    validate_callback_url,
)

__all__ = [
    "KID_SANDBOX_V1",
    "OutboundCanonicalRequest",
    "WebhookUrlValidationResult",
    "build_outbound_canonical_request",
    "compute_outbound_signature",
    "validate_callback_url",
    "verify_outbound_signature",
]
