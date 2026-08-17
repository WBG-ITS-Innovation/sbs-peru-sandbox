# SPDX-License-Identifier: Apache-2.0
"""POST /v1/oauth/token — OAuth 2.0 client_credentials grant per ADR 0032.

Request shape (RFC 6749 §2.3.1 + §4.4):

* ``Content-Type: application/x-www-form-urlencoded``
* Form fields: ``grant_type=client_credentials``, ``scope=...``
* ``Authorization: Basic <base64(client_id:client_secret)>``
* Valid mTLS connection (the cert is bound into the token via
  ``cnf.x5t#S256``).

Response (RFC 6749 §5.1, success):

```
{
  "access_token": "<jwt>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "complaints:write batch:upload"
}
```

Error responses follow RFC 6749 §5.2 with stable codes from the SBS
error catalogue (INVALID_REQUEST, INVALID_GRANT, INVALID_SCOPE,
TOKEN_CERT_REQUIRED).
"""

from __future__ import annotations

import base64
import binascii

from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.auth.oauth import (
    IssueOptions,
    issue_token,
    verify_client_secret,
)
from sbs_api.auth.scopes import ALL_SCOPES, parse_scope_param
from sbs_api.db.models.institution import InstitutionRecord
from sbs_api.db.models.oauth_client import OAuthClient
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.mtls import MtlsSubject, verified_mtls_subject
from sbs_api.dependencies.oauth import get_signing_key
from sbs_api.dependencies.rate_limit import oauth_token_bucket
from sbs_api.errors.exceptions import (
    OAuthInvalidGrant,
    OAuthInvalidRequest,
    OAuthInvalidScope,
)

router = APIRouter(prefix="/oauth", tags=["oauth"])


def _decode_basic(header: str) -> tuple[str, str]:
    if not header:
        raise OAuthInvalidRequest(detail="Missing Authorization header.")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "basic" or not value:
        raise OAuthInvalidRequest(
            detail="Authorization header must be 'Basic <base64(client_id:client_secret)>'."
        )
    try:
        raw = base64.b64decode(value.strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise OAuthInvalidRequest(
            detail="Authorization Basic value is not valid base64 UTF-8."
        ) from exc
    if ":" not in raw:
        raise OAuthInvalidRequest(
            detail="Basic value must be client_id:client_secret."
        )
    client_id, _, client_secret = raw.partition(":")
    return client_id, client_secret


@router.post(
    "/token",
    summary="OAuth 2.0 client_credentials token endpoint",
)
async def token_endpoint(
    request: Request,
    grant_type: str = Form(...),
    scope: str = Form(""),
    # `oauth_token_bucket` transitively depends on verified_mtls_subject,
    # so we ask FastAPI for the bucket and receive the same mTLS subject
    # back. The bucket enforces 50/min on POST /v1/oauth/token per the
    # ADR 0033 pressure-test amendment.
    mtls_subject: MtlsSubject = Depends(oauth_token_bucket),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if grant_type != "client_credentials":
        raise OAuthInvalidRequest(
            detail=(
                f"Unsupported grant_type {grant_type!r}. Only "
                "'client_credentials' is supported."
            )
        )

    client_id, presented_secret = _decode_basic(
        request.headers.get("authorization", "")
    )

    # Look up the client.
    stmt = select(OAuthClient).where(OAuthClient.client_id == client_id)
    result = await session.execute(stmt)
    client_row = result.scalar_one_or_none()
    if client_row is None or client_row.disabled_at is not None:
        raise OAuthInvalidGrant(detail="Unknown or disabled client_id.")

    if client_row.institution_id != mtls_subject.institution_id:
        # Client credentials must belong to the institution presenting
        # the cert. A bank's credentials cannot fetch a token under a
        # different institution's cert.
        raise OAuthInvalidGrant(
            detail="client_id does not belong to the mTLS-presenting institution."
        )

    if not verify_client_secret(presented_secret, client_row.client_secret_hash):
        raise OAuthInvalidGrant(detail="Invalid client_secret.")

    if (
        client_row.cert_thumbprint_required is not None
        and client_row.cert_thumbprint_required.lower()
        != mtls_subject.cert_thumbprint.lower()
    ):
        raise OAuthInvalidGrant(
            detail=(
                "Client is bound to a different cert thumbprint than the "
                "one presenting in this connection."
            )
        )

    # Resolve permitted scopes from the institution row.
    inst_stmt = select(InstitutionRecord.permitted_scopes).where(
        InstitutionRecord.institution_id == mtls_subject.institution_id
    )
    inst_result = await session.execute(inst_stmt)
    permitted = set(inst_result.scalar_one_or_none() or [])
    permitted &= ALL_SCOPES  # defence against stale rows with unknown scopes

    requested = parse_scope_param(scope) if scope else permitted
    unknown = requested - ALL_SCOPES
    if unknown:
        raise OAuthInvalidScope(
            detail=f"Unknown scope(s) in request: {sorted(unknown)}."
        )

    granted = requested & permitted
    if not granted:
        raise OAuthInvalidScope(
            detail=(
                "No requested scopes are permitted for this institution. "
                f"Requested={sorted(requested)} permitted={sorted(permitted)}."
            )
        )

    options = IssueOptions(
        institution_id=mtls_subject.institution_id,
        granted_scopes=frozenset(granted),
        cert_thumbprint_sha256_hex=mtls_subject.cert_thumbprint,
    )
    access_token = issue_token(options, key=get_signing_key())

    # Returning a dict lets FastAPI merge the X-RateLimit-* headers set
    # by the oauth_token_bucket dependency on the response parameter.
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": options.ttl_seconds,
        "scope": " ".join(sorted(granted)),
    }
