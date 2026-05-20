"""HMAC signature verification dependency — workstream B (ADR 0027 amendment).

Runs after :func:`verified_mtls_subject` so the institution_id is already
resolved and bound to a cert thumbprint. The dependency:

1. Reads ``X-SBS-Timestamp`` and ``X-SBS-Signature`` headers.
2. Validates the timestamp window (5-min past, 60-sec future).
3. Reads the raw request body (cached by the body-size-limit middleware).
4. Looks up the institution_secret row; tries ``active_secret`` first,
   then ``previous_secret`` if the rotation grace is still active.
5. Constructs the canonical request and verifies the signature.
6. Cross-checks the institution_id encoded in the canonical request
   against the mTLS subject's institution_id.
7. Claims the signature in the Redis replay cache; second-seen returns
   ``SIGNATURE_REPLAYED``.

This is a dependency, not middleware, so it can:
* depend on :func:`verified_mtls_subject` for the institution_id
* depend on :func:`get_session` for the secrets lookup
* raise :class:`SBSAPIException` cleanly (handler renders ProblemDetail)

The middleware framing in the ADR text is loose; the contract — that
every authenticated request is HMAC-verified — is preserved.
"""

from __future__ import annotations

from datetime import datetime, timezone

import redis.asyncio as redis_async
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.auth.hmac import (
    build_canonical_request,
    parse_signature_header,
    replay_cache_key,
    validate_timestamp,
    verify_signature,
)
from sbs_api.config import Settings, get_settings
from sbs_api.db.models.institution_secret import InstitutionSecret
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.mtls import MtlsSubject, verified_mtls_subject
from sbs_api.errors.exceptions import (
    HmacSecretNotConfigured,
    SignatureAlgorithmUnsupported,
    SignatureExpired,
    SignatureInstitutionMismatch,
    SignatureInvalid,
    SignatureMissingHeader,
    SignatureReplayed,
)

TIMESTAMP_HEADER = "x-sbs-timestamp"
SIGNATURE_HEADER = "x-sbs-signature"


# ---------------------------------------------------------------------------
# Redis client management
# ---------------------------------------------------------------------------

_redis_client: redis_async.Redis | None = None


def get_redis_client() -> redis_async.Redis:
    """Lazy global client, like the SQLAlchemy engine.

    Tests override this via :func:`override_redis_for_test` so the
    fakeredis-backed client is used.
    """

    global _redis_client
    if _redis_client is None:
        from sbs_api.config import get_settings

        settings = get_settings()
        url = getattr(settings, "redis_url", None) or "redis://localhost:6379/0"
        _redis_client = redis_async.from_url(url, decode_responses=False)
    return _redis_client


def override_redis_for_test(client: redis_async.Redis) -> None:
    """Inject a test-controlled Redis client (e.g. fakeredis)."""

    global _redis_client
    _redis_client = client


def reset_redis_for_test() -> None:
    """Drop the cached client so the next get_redis_client() rebuilds."""

    global _redis_client
    _redis_client = None


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


async def verified_hmac_signature(
    request: Request,
    mtls_subject: MtlsSubject = Depends(verified_mtls_subject),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> MtlsSubject:
    """Verify the HMAC signature; return the mTLS subject on success.

    Returning the subject is a convenience so route handlers that need
    institution_id can declare a single dependency instead of two.
    """

    # --- 1. Headers ---------------------------------------------------
    timestamp = request.headers.get(TIMESTAMP_HEADER)
    sig_header = request.headers.get(SIGNATURE_HEADER)
    if not timestamp:
        raise SignatureMissingHeader(detail=f"Missing {TIMESTAMP_HEADER} header.")
    if not sig_header:
        raise SignatureMissingHeader(detail=f"Missing {SIGNATURE_HEADER} header.")

    # --- 2. Algorithm prefix + signature -----------------------------
    try:
        sig_b64 = parse_signature_header(sig_header)
    except ValueError as exc:
        raise SignatureAlgorithmUnsupported(detail=str(exc)) from exc

    # --- 3. Timestamp window -----------------------------------------
    verdict = validate_timestamp(
        timestamp,
        now=datetime.now(timezone.utc),
        skew_seconds=settings.hmac_timestamp_skew_seconds,
    )
    if not verdict.valid:
        raise SignatureExpired(detail=verdict.reason or "timestamp invalid")

    # --- 4. Body -----------------------------------------------------
    body = await request.body()

    # ADR 0027 amendment (multipart body-hash definition): for
    # multipart/form-data requests, the canonical-request body-hash is
    # taken over the *file* part's bytes only, not the multipart
    # envelope. Rationale: the manifest already declares the CSV's
    # SHA-256 as a verifiable field, and the multipart boundary
    # encoding is implementation-detail-dependent. Practically: this
    # lets the institution's signing client compute one hash (over the
    # file it is uploading) and the server's verifier compute the same
    # hash on receipt.
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        file_part = form.get("file")
        if file_part is None or not hasattr(file_part, "read"):
            raise SignatureMissingHeader(
                detail=(
                    "Multipart request missing 'file' part; the canonical "
                    "request body-hash is computed over the file bytes per "
                    "ADR 0027 amendment, so the 'file' part is required."
                )
            )
        await file_part.seek(0)
        body = await file_part.read()
        # Rewind so downstream handlers can read the file again.
        await file_part.seek(0)

    # --- 5. Host header ---------------------------------------------
    host = request.headers.get("host", "")
    if not host:
        # ASGITransport may omit Host; canonicalise to the literal
        # 'testserver' default httpx uses to keep tests deterministic.
        # Confined to test environment — production paths must carry
        # an explicit Host header (otherwise a proxy that strips Host
        # could create a canonical-request ambiguity an attacker
        # could exploit).
        if settings.environment == "test":
            host = "testserver"
        else:
            raise SignatureMissingHeader(
                detail=(
                    "Request is missing the Host header; HMAC canonical "
                    "request cannot be reconstructed unambiguously."
                )
            )

    # --- 6. Institution_id from header for cross-check ---------------
    # The signed institution_id is part of the canonical string; the
    # canonical-request *requires* a value, but the value the client
    # signed must equal the mTLS-resolved institution_id. The simplest
    # protocol shape: the client puts their institution_id in a
    # convention header (`X-SBS-Institution-Id`) AND signs it; the
    # server reads from header for canonical-request construction and
    # then cross-checks against the mTLS subject.
    header_iid = request.headers.get("x-sbs-institution-id", "").strip()
    if not header_iid:
        raise SignatureMissingHeader(
            detail="Missing X-SBS-Institution-Id header."
        )

    target = request.url.path
    if request.url.query:
        target = f"{target}?{request.url.query}"
    canonical = build_canonical_request(
        method=request.method,
        target=target,
        host=host,
        timestamp=timestamp,
        body=body,
        institution_id=header_iid,
    )

    # --- 7. Cross-check institution_id ------------------------------
    if header_iid != mtls_subject.institution_id:
        raise SignatureInstitutionMismatch(
            detail=(
                f"X-SBS-Institution-Id={header_iid!r} does not match the "
                f"mTLS subject's institution_id={mtls_subject.institution_id!r}."
            )
        )

    # --- 8. Load secret(s) ------------------------------------------
    stmt = select(InstitutionSecret).where(
        InstitutionSecret.institution_id == mtls_subject.institution_id
    )
    result = await session.execute(stmt)
    secret_row = result.scalar_one_or_none()
    if secret_row is None:
        raise HmacSecretNotConfigured(
            detail=(
                f"No HMAC secret configured for institution "
                f"{mtls_subject.institution_id}. Onboarding incomplete."
            )
        )

    # --- 9. Verify against active, then previous (if in grace) -------
    if verify_signature(bytes(secret_row.active_secret), canonical, sig_b64):
        verified = True
    elif (
        secret_row.previous_secret is not None
        and secret_row.previous_secret_retires_at is not None
        and secret_row.previous_secret_retires_at > datetime.now(timezone.utc)
        and verify_signature(
            bytes(secret_row.previous_secret), canonical, sig_b64
        )
    ):
        verified = True
    else:
        verified = False

    if not verified:
        raise SignatureInvalid(
            detail="HMAC signature does not match the canonical request."
        )

    # --- 10. Replay-cache claim --------------------------------------
    key = replay_cache_key(mtls_subject.institution_id, sig_b64)
    client = get_redis_client()
    # SET key 1 NX EX <ttl> — atomic claim. Returns None if already set.
    claimed = await client.set(
        key, b"1", nx=True, ex=settings.hmac_replay_cache_ttl_seconds
    )
    if not claimed:
        raise SignatureReplayed(
            detail=(
                "This signature has already been seen within the replay "
                "window. Sign a fresh request with a current timestamp."
            )
        )

    return mtls_subject
