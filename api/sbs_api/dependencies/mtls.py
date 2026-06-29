# SPDX-License-Identifier: Apache-2.0
"""mTLS subject extraction — ADR 0031 (with pressure-test amendments).

Two modes, gated on :data:`Settings.mtls_mode`:

* ``direct`` — uvicorn terminates TLS, the peer cert is in ``request.scope``.
  We compute the SHA-256 thumbprint over the DER encoding.
* ``proxy`` — the reverse proxy terminates TLS, validates the cert chain,
  and forwards the verified metadata in the ``X-Forwarded-Client-Cert``
  header (XFCC, Envoy de-facto standard). We parse the outermost
  (rightmost) element of the comma-separated header for ``Hash=`` and
  ``Subject="CN=..."``.

In either mode the dependency returns the same :class:`MtlsSubject` so
downstream OAuth and HMAC dependencies do not care which mode is active.

The CN→institution_id resolution looks up ``institution_certificates`` by
``sha256_thumbprint``. A valid cert whose thumbprint is not on file
returns 403 ``CERT_CN_UNKNOWN``; a thumbprint on file but with a
populated ``revoked_at`` returns 403 ``CERT_REVOKED``; an expired cert
returns 401 ``CERT_EXPIRED``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.config import Settings, get_settings
from sbs_api.db.models.institution_certificate import InstitutionCertificate
from sbs_api.dependencies.db import get_session
from sbs_api.errors.exceptions import (
    CertCnUnknown,
    CertExpired,
    CertInvalid,
    CertRequired,
    CertRevoked,
)


@dataclass(frozen=True)
class MtlsSubject:
    """Verified institutional identity from the mTLS layer."""

    institution_id: str
    cn: str
    cert_thumbprint: str  # lowercase hex SHA-256 of DER cert


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------

# Envoy emits XFCC like:
#   By=spiffe://...;Hash=<hex>;Subject="CN=BANCO_DEMO_001,O=...";URI=spiffe://...
# Multiple elements separated by commas at the top level (one per hop).
# Per RFC 7239-style semantics we trust the rightmost element written by
# our trusted proxy. The fields within an element are `;`-separated.
_FIELD_RE = re.compile(r'([A-Za-z]+)=("([^"]*)"|([^;,]+))')


def _split_xfcc_elements(header_value: str) -> list[str]:
    """Split the XFCC header on top-level commas, respecting double quotes.

    Subject values are quoted and may contain commas (e.g.
    ``Subject="CN=BANCO_DEMO_001,O=SBS"``). A naive ``.split(",")`` would
    break those values; this helper tracks quote state.
    """

    elements: list[str] = []
    current: list[str] = []
    in_quotes = False
    for ch in header_value:
        if ch == '"':
            in_quotes = not in_quotes
            current.append(ch)
        elif ch == "," and not in_quotes:
            piece = "".join(current).strip()
            if piece:
                elements.append(piece)
            current = []
        else:
            current.append(ch)
    tail = "".join(current).strip()
    if tail:
        elements.append(tail)
    return elements


def _parse_xfcc(header_value: str) -> dict[str, str]:
    """Parse the outermost (rightmost) XFCC element into a field dict.

    Returns an empty dict if no recognisable fields are present. Envoy
    appends its element rightmost, so we trust the last one.
    """

    elements = _split_xfcc_elements(header_value)
    if not elements:
        return {}
    last = elements[-1]
    fields: dict[str, str] = {}
    for match in _FIELD_RE.finditer(last):
        key = match.group(1)
        quoted = match.group(3)
        unquoted = match.group(4)
        fields[key] = quoted if quoted is not None else (unquoted or "")
    return fields


_CN_RE = re.compile(r'CN=([^,/]+)')


def _extract_cn(subject: str) -> str | None:
    """Pull the CN value out of an RFC 2253 / OpenSSL-style subject string.

    Handles both `CN=...` and `/CN=...` forms; returns None if absent.
    """

    if not subject:
        return None
    match = _CN_RE.search(subject)
    if not match:
        return None
    return match.group(1).strip()


def _peer_cert_der_from_request(request: Request) -> bytes | None:
    """Read the verified peer cert DER bytes off ``request.state``.

    The :class:`MtlsTransportCaptureMiddleware` ASGI middleware
    (installed in :func:`sbs_api.app.create_app`) walks the asyncio
    task at request entry to find uvicorn\'s ``RequestResponseCycle``,
    extracts the peer cert DER from the SSL transport, and stashes it
    at ``request.state.peer_cert_der``. This dependency only reads.

    Uvicorn 0.47 does not implement the ASGI TLS extension
    (``scope[\'extensions\']["tls"]``); the middleware is the bridge
    until we upgrade or switch to hypercorn (Part 9).
    """

    return getattr(request.state, "peer_cert_der", None)


def _direct_mode_extract(request: Request) -> tuple[str, str]:
    """Return (cn, thumbprint_hex) from the connection's verified peer cert.

    Uvicorn 0.47 does not implement the ASGI TLS extension, so we reach
    into its internal :class:`RequestResponseCycle` to find the
    ``_SSLProtocolTransport`` and pull the verified peer cert DER bytes
    from the underlying SSL socket (see :func:`_peer_cert_der_from_uvicorn`).
    The TLS handshake has already validated the chain against the CA at
    this point — we're only reading what uvicorn already accepted.
    """

    der_bytes = _peer_cert_der_from_request(request)
    if der_bytes is None:
        raise CertRequired(
            detail="No client certificate was presented to the TLS layer."
        )

    # Lazy import: cryptography pulls in OpenSSL at import; tests that
    # never exercise direct mode should not pay the cost.
    try:
        from cryptography import x509
    except ImportError as exc:  # pragma: no cover
        raise CertInvalid(
            detail=f"cryptography library not installed: {exc}"
        ) from exc

    try:
        cert = x509.load_der_x509_certificate(der_bytes)
    except (ValueError, TypeError) as exc:
        raise CertInvalid(detail=f"Could not parse client certificate: {exc}") from exc

    thumbprint = hashlib.sha256(der_bytes).hexdigest()

    cn_attrs = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
    if not cn_attrs:
        raise CertInvalid(
            detail="Client certificate has no CN attribute in the subject DN."
        )
    cn = cn_attrs[0].value
    if not isinstance(cn, str):  # cryptography returns str or bytes
        cn = cn.decode("utf-8")

    return cn, thumbprint


def _proxy_mode_extract(request: Request, settings: Settings) -> tuple[str, str]:
    """Return (cn, thumbprint_hex) from the proxy-forwarded XFCC header."""

    header_value = request.headers.get(settings.proxy_trusted_xfcc_header)
    if not header_value:
        raise CertRequired(
            detail=(
                f"Proxy mode expects the {settings.proxy_trusted_xfcc_header} "
                "header. The reverse proxy is misconfigured or the request "
                "did not present a client certificate."
            )
        )

    fields = _parse_xfcc(header_value)
    thumbprint = fields.get("Hash", "").lower()
    subject = fields.get("Subject", "")
    cn = _extract_cn(subject)

    if not thumbprint:
        raise CertInvalid(
            detail="XFCC header is missing the Hash= field required for cert binding."
        )
    if not cn:
        raise CertInvalid(
            detail="XFCC header is missing a parseable CN in the Subject= field."
        )
    # Validate the thumbprint is well-formed hex (64 chars for SHA-256).
    if len(thumbprint) != 64 or not all(c in "0123456789abcdef" for c in thumbprint):
        raise CertInvalid(
            detail="XFCC Hash= field is not a 64-char lowercase hex SHA-256 thumbprint."
        )

    return cn, thumbprint


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def verified_mtls_subject(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MtlsSubject:
    """Resolve the institution_id from the connection's mTLS subject.

    The return value is the input to:
    * the OAuth token-binding check (ADR 0032 ``cnf.x5t#S256``)
    * the HMAC institution_id cross-check (ADR 0027 amendment)
    """

    if settings.disable_mtls_for_tests:
        # Tests that don't exercise the mTLS layer should override this
        # dependency directly. The escape hatch returns a sentinel that
        # makes the bypass obvious in logs.
        return MtlsSubject(
            institution_id="SBS-001234",
            cn="BANCO_DEMO_001",
            cert_thumbprint="0" * 64,
        )

    if settings.mtls_mode == "direct":
        cn, thumbprint = _direct_mode_extract(request)
    elif settings.mtls_mode == "proxy":
        cn, thumbprint = _proxy_mode_extract(request, settings)
    else:
        raise CertRequired(
            detail=(
                "mTLS is not configured. Set SBS_API_MTLS_MODE=direct "
                "(uvicorn termination) or proxy (reverse-proxy termination)."
            )
        )

    stmt = select(InstitutionCertificate).where(
        InstitutionCertificate.sha256_thumbprint == thumbprint
    )
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        raise CertCnUnknown(
            detail=(
                f"Certificate with CN={cn} is valid but no matching "
                "institution_certificates row exists. The institution may "
                "not yet be onboarded, or the cert may be from a different CA."
            )
        )
    if record.revoked_at is not None:
        raise CertRevoked(
            detail=f"Certificate for CN={cn} was revoked at {record.revoked_at.isoformat()}."
        )

    now = datetime.now(timezone.utc)
    if record.not_after <= now:
        raise CertExpired(
            detail=f"Certificate for CN={cn} expired at {record.not_after.isoformat()}."
        )
    # not_before is checked by the TLS layer in direct mode; in proxy mode
    # the proxy already enforced it. We still guard against clock skew
    # on the registry row.
    if record.not_before > now:
        raise CertInvalid(
            detail=f"Certificate for CN={cn} is not yet valid (notBefore={record.not_before.isoformat()})."
        )

    return MtlsSubject(
        institution_id=record.institution_id,
        cn=record.cn,
        cert_thumbprint=thumbprint,
    )
