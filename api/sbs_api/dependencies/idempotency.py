"""Idempotency-Key handling.

ADR 0029 — POST and PATCH unsafe operations accept ``Idempotency-Key``.
On first execution the response (status + body + a small allowlist of
headers) is cached for ``IDEMPOTENCY_TTL_SECONDS``. Replay with the same
body returns the cached response with ``Idempotency-Replayed: true``;
replay with a different body returns 409 ``IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_BODY``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import uuid_utils as uuid7
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.config import get_settings
from sbs_api.db.models.idempotency import IdempotencyRecord
from sbs_api.errors.exceptions import IdempotencyKeyReuseWithDifferentBody


@dataclass(frozen=True)
class IdempotencyContext:
    institution_id: str
    key: str
    body: bytes
    body_sha256: bytes
    method: str
    path: str


def body_sha256(body: bytes) -> bytes:
    return hashlib.sha256(body).digest()


def get_idempotency_context(
    institution_id: str, key: str, body: bytes, method: str, path: str
) -> IdempotencyContext:
    return IdempotencyContext(
        institution_id=institution_id,
        key=key,
        body=body,
        body_sha256=body_sha256(body),
        method=method,
        path=path,
    )


async def lookup_cached(
    session: AsyncSession, ctx: IdempotencyContext
) -> IdempotencyRecord | None:
    """Return a matching, non-expired record, or None.

    On a body-hash mismatch raises :class:`IdempotencyKeyReuseWithDifferentBody`
    so the caller does not need to compare hashes explicitly.
    """

    stmt = select(IdempotencyRecord).where(
        IdempotencyRecord.institution_id == ctx.institution_id,
        IdempotencyRecord.idempotency_key == ctx.key,
    )
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None:
        return None
    if record.expires_at <= datetime.now(timezone.utc):
        return None
    if bytes(record.body_sha256) != ctx.body_sha256:
        raise IdempotencyKeyReuseWithDifferentBody(
            detail=(
                "Idempotency-Key was reused within the 24-hour window but the "
                "request body hash differs from the original. Use a fresh "
                "Idempotency-Key for the new request, or replay the original "
                "body verbatim."
            )
        )
    return record


async def store(
    session: AsyncSession,
    ctx: IdempotencyContext,
    *,
    status: int,
    body: dict,
    headers: dict[str, str],
) -> IdempotencyRecord:
    """Persist a fresh idempotency record."""

    settings = get_settings()
    record = IdempotencyRecord(
        record_id=str(uuid7.uuid7()).replace("-", ""),
        institution_id=ctx.institution_id,
        idempotency_key=ctx.key,
        body_sha256=ctx.body_sha256,
        response_status=status,
        response_payload=json.dumps(body, default=str),
        response_headers=json.dumps(headers),
        request_method=ctx.method,
        request_path=ctx.path,
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=settings.idempotency_ttl_seconds),
    )
    session.add(record)
    await session.flush()
    return record
