# SPDX-License-Identifier: Apache-2.0
"""Rate-limit FastAPI dependencies — ADR 0033 with pressure-test amendments.

Two pre-built dependencies:

* :func:`business_bucket` — per-institution_id, tier-aware. Tier
  defaults from Settings (``rate_limit_tier_{large,small}_per_minute``),
  overridable by ``institutions.rate_limit_per_minute``.
* :func:`oauth_token_bucket` — tighter, keyed on the mTLS CN (the OAuth
  token has not been issued at this point, so institution_id may not
  yet be resolved when the bucket runs). Flat 50/min default per
  pressure-test amendment.

Both dependencies set the four X-RateLimit-* / Retry-After headers on
the response. On exhaustion they raise :class:`RateLimitExceeded` (or
:class:`TokenEndpointRateLimitExceeded`) with those headers in
``extra_headers`` so the ProblemDetail 429 carries them too.
"""

from __future__ import annotations

from typing import Callable

import redis.asyncio as redis_async
from fastapi import Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.config import Settings, get_settings
from sbs_api.db.models.institution import InstitutionRecord
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.hmac_verify import get_redis_client
from sbs_api.dependencies.mtls import MtlsSubject, verified_mtls_subject
from sbs_api.errors.exceptions import (
    RateLimitExceeded,
    TokenEndpointRateLimitExceeded,
)
from sbs_api.rate_limit.token_bucket import BucketDecision, decrement_bucket


def _apply_headers(response: Response, decision: BucketDecision) -> None:
    response.headers["X-RateLimit-Limit"] = str(decision.limit)
    response.headers["X-RateLimit-Remaining"] = str(max(0, decision.remaining))
    response.headers["X-RateLimit-Reset"] = str(decision.reset_unix_ms // 1000)


def _make_429_headers(decision: BucketDecision) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(decision.limit),
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": str(decision.reset_unix_ms // 1000),
        "Retry-After": str(decision.retry_after_seconds),
    }


# ---------------------------------------------------------------------------
# Business bucket — per institution_id, tier-aware
# ---------------------------------------------------------------------------


async def _resolve_institution_limit(
    session: AsyncSession,
    *,
    institution_id: str,
    settings: Settings,
) -> int:
    """Return the effective per-minute limit for this institution.

    Walks the override → tier default fallback.
    """

    stmt = select(
        InstitutionRecord.tier_classification,
        InstitutionRecord.rate_limit_per_minute,
    ).where(InstitutionRecord.institution_id == institution_id)
    result = await session.execute(stmt)
    row = result.one_or_none()
    if row is None:
        # Institution not yet onboarded — treat as small to stay safe.
        return settings.rate_limit_tier_small_per_minute
    tier, override = row
    if override is not None:
        return int(override)
    if tier == "large":
        return settings.rate_limit_tier_large_per_minute
    # Default and explicit 'small' fall through here.
    return settings.rate_limit_tier_small_per_minute


async def business_bucket(
    response: Response,
    mtls_subject: MtlsSubject = Depends(verified_mtls_subject),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    redis_client: redis_async.Redis = Depends(get_redis_client),
) -> MtlsSubject:
    """Per-institution rate limit. Raises 429 with the four headers on overrun."""

    limit = await _resolve_institution_limit(
        session, institution_id=mtls_subject.institution_id, settings=settings
    )
    decision = await decrement_bucket(
        redis_client,
        key=f"sbs:rate:business:{mtls_subject.institution_id}",
        limit=limit,
    )
    if not decision.allowed:
        raise RateLimitExceeded(
            detail=(
                f"Institution {mtls_subject.institution_id} exceeded "
                f"its limit of {limit} requests/minute. Retry after "
                f"{decision.retry_after_seconds} seconds."
            ),
            extra_headers=_make_429_headers(decision),
        )
    _apply_headers(response, decision)
    return mtls_subject


# ---------------------------------------------------------------------------
# OAuth token-endpoint bucket — keyed on mTLS CN (pre-token), flat 50/min
# ---------------------------------------------------------------------------


async def oauth_token_bucket(
    response: Response,
    mtls_subject: MtlsSubject = Depends(verified_mtls_subject),
    settings: Settings = Depends(get_settings),
    redis_client: redis_async.Redis = Depends(get_redis_client),
) -> MtlsSubject:
    """Tighter bucket for POST /v1/oauth/token. Keyed on mTLS CN."""

    limit = settings.rate_limit_token_endpoint_per_minute
    decision = await decrement_bucket(
        redis_client,
        key=f"sbs:rate:oauth_token:{mtls_subject.cn}",
        limit=limit,
    )
    if not decision.allowed:
        raise TokenEndpointRateLimitExceeded(
            detail=(
                f"Token endpoint for CN={mtls_subject.cn} exceeded its "
                f"limit of {limit} requests/minute. Retry after "
                f"{decision.retry_after_seconds} seconds."
            ),
            extra_headers=_make_429_headers(decision),
        )
    _apply_headers(response, decision)
    return mtls_subject
