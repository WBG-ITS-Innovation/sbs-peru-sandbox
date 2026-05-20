"""Outbound webhook URL validation (ADR 0035 §webhook-url-validation).

Three checks, all mandatory unless ``settings.allow_insecure_webhook_urls``
is True AND ``settings.environment in {dev, test}`` (the latter gate is
enforced at app boot in :func:`sbs_api.app.create_app`, so by the time
this code runs the env-gated override is safe to honour):

1. **HTTPS-only** — reject ``http://``. Production webhook traffic
   should not be intercepted by an in-network attacker.
2. **FQDN-only** — reject bare hostnames (e.g. ``listener``) and IP
   literals. The bare-hostname check is a soft proxy for "we're being
   asked to deliver to something that won't resolve outside our
   network".
3. **Public-IP-only** — resolve the host and reject if the resolved
   address is in any of: RFC 1918 (10/8, 172.16/12, 192.168/16),
   link-local (169.254/16), loopback (127/8), CGNAT (100.64/10),
   private IPv6 (fc00::/7, fe80::/10, ::1), or the AWS-style
   instance-metadata address ``169.254.169.254``.

A bypass via the env knob is the only acceptable path to a private-IP
callback. The dev / test override is necessary for the compose-internal
``webhook-listener`` service to receive the demo callbacks.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from sbs_api.config import get_settings

# AWS-style instance-metadata IPs (the canonical one + the link-local pair).
_BLOCKED_LITERAL_IPS = {
    "169.254.169.254",
    "fd00:ec2::254",
}


@dataclass(frozen=True)
class WebhookUrlValidationResult:
    valid: bool
    reason: str | None = None  # set when valid=False
    code: str = "WEBHOOK_URL_REJECTED"
    # The address the host resolved to at validation time. Callers pin
    # the HTTP connection to this IP to close the DNS-rebinding TOCTOU
    # window (second-opinion finding, Workstream D closeout).
    resolved_address: str | None = None


def _looks_like_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def _is_fqdn(host: str) -> bool:
    """Heuristic: host contains at least one dot and is not an IP literal.

    Not RFC-strict; the goal is to reject bare hostnames like
    ``webhook-listener`` while accepting ``webhook.example.com``.
    """

    if _looks_like_ip_literal(host):
        return False
    return "." in host


def _resolve_addresses(host: str) -> list[str]:
    """Return all addresses ``getaddrinfo`` reports for ``host``.

    On any resolution error returns an empty list — the caller treats
    that as a validation failure (we cannot deliver to a name that
    does not resolve).
    """

    try:
        results = socket.getaddrinfo(
            host, None, type=socket.SOCK_STREAM
        )
    except OSError:
        return []
    addrs: list[str] = []
    for res in results:
        sockaddr = res[4]
        if sockaddr and isinstance(sockaddr[0], str):
            addrs.append(sockaddr[0])
    return addrs


def _is_public_ip(addr: str) -> bool:
    if addr in _BLOCKED_LITERAL_IPS:
        return False
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_callback_url(url: str) -> WebhookUrlValidationResult:
    """Validate ``url`` per ADR 0035 §webhook-url-validation.

    Returns a :class:`WebhookUrlValidationResult`. Callers act on the
    ``valid`` flag and store ``reason`` + ``code`` in
    ``webhook_deliveries.failure_reason`` on rejection.

    The env override (``settings.allow_insecure_webhook_urls``) skips
    all three checks. The startup-time guard in
    :func:`sbs_api.app.create_app` already refuses to boot with the
    override set in staging or prod, so honouring it here is safe.
    """

    settings = get_settings()
    if settings.allow_insecure_webhook_urls:
        return WebhookUrlValidationResult(valid=True)

    try:
        parsed = urlparse(url)
    except ValueError as exc:
        return WebhookUrlValidationResult(
            valid=False, reason=f"URL parse failed: {exc}"
        )

    if parsed.scheme != "https":
        return WebhookUrlValidationResult(
            valid=False,
            reason=(
                f"scheme must be https; received {parsed.scheme!r}. "
                "Webhook URLs are HTTPS-only outside dev/test."
            ),
        )

    host = parsed.hostname or ""
    if not host:
        return WebhookUrlValidationResult(
            valid=False, reason="URL missing host."
        )

    if not _is_fqdn(host):
        return WebhookUrlValidationResult(
            valid=False,
            reason=(
                f"host {host!r} is not a fully-qualified domain name. "
                "Bare hostnames and IP literals are not permitted "
                "outside dev/test."
            ),
        )

    addresses = _resolve_addresses(host)
    if not addresses:
        return WebhookUrlValidationResult(
            valid=False,
            reason=f"host {host!r} did not resolve to any address.",
        )

    for addr in addresses:
        if not _is_public_ip(addr):
            return WebhookUrlValidationResult(
                valid=False,
                reason=(
                    f"host {host!r} resolves to non-public address "
                    f"{addr!r} (private/loopback/link-local/metadata)."
                ),
            )

    # Pin the first resolved address; the caller dials this IP rather
    # than letting httpx re-resolve. Closes the DNS-rebinding TOCTOU
    # window flagged in the Prompt 8 second-opinion review.
    return WebhookUrlValidationResult(
        valid=True, resolved_address=addresses[0]
    )
