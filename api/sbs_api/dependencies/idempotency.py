# SPDX-License-Identifier: Apache-2.0
"""Idempotency-Key handling.

ADR 0029 — POST and PATCH unsafe operations accept ``Idempotency-Key``.
On first execution the response (status + body + a small allowlist of
headers) is cached for ``IDEMPOTENCY_TTL_SECONDS``. Replay with the same
body returns the cached response with ``Idempotency-Replayed: true``;
replay with a different body returns 409 ``IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_BODY``.

ADR 0029 amendment (Prompt 7 F.1) — concurrent-POST policy. The handler
INSERTs a placeholder row with ``state='processing'`` under the unique
constraint ``(institution_id, idempotency_key)`` in a short transaction
so the placeholder is visible to concurrent workers immediately. The
handler then proceeds with the business logic and UPDATEs the row to
``state='complete'`` with the response. A concurrent second request
whose INSERT loses the race reads the existing row; if state='complete'
it returns the cached response, otherwise it waits 50ms × 3 retries
for the first to finish, then 409 ``IDEMPOTENCY_KEY_IN_FLIGHT``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import uuid_utils as uuid7
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sbs_api.config import get_settings
from sbs_api.db.models.idempotency import IdempotencyRecord
from sbs_api.db.session import get_sessionmaker
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


# ---------------------------------------------------------------------------
# Concurrent-POST claim helper (ADR 0029 amendment)
# ---------------------------------------------------------------------------


ClaimState = Literal["claimed", "replay", "in_flight"]


@dataclass(frozen=True)
class ClaimResult:
    state: ClaimState
    record: IdempotencyRecord | None = None


async def claim_idempotency_slot(
    sessionmaker: async_sessionmaker[AsyncSession],
    ctx: IdempotencyContext,
    *,
    retry_delay_ms: int = 50,
    max_retries: int = 3,
) -> ClaimResult:
    """Claim a fresh idempotency slot, or read the existing row.

    Returns:
      ``ClaimResult(state="claimed")``  — caller owns the slot; proceed.
      ``ClaimResult(state="replay", record=...)`` — existing complete
                                                    record; return cached.
      ``ClaimResult(state="in_flight")`` — concurrent in-flight, no
                                            result after 150ms. Caller
                                            should raise IDEMPOTENCY_KEY_IN_FLIGHT.

    Raises :class:`IdempotencyKeyReuseWithDifferentBody` when the
    existing row has a different body hash than this request.
    """

    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.idempotency_ttl_seconds
    )
    record_id = str(uuid7.uuid7()).replace("-", "")

    # First attempt: INSERT a placeholder in a short, dedicated transaction
    # so the row is visible to concurrent workers immediately.
    async with sessionmaker() as session:
        try:
            async with session.begin():
                session.add(
                    IdempotencyRecord(
                        record_id=record_id,
                        institution_id=ctx.institution_id,
                        idempotency_key=ctx.key,
                        body_sha256=ctx.body_sha256,
                        response_status=0,
                        response_payload="",
                        response_headers="{}",
                        request_method=ctx.method,
                        request_path=ctx.path,
                        state="processing",
                        expires_at=expires_at,
                    )
                )
            return ClaimResult(state="claimed")
        except IntegrityError:
            pass  # fall through to the read+wait path

    # Conflict path: the row exists. Read it, retrying briefly if it
    # is still in 'processing' state.
    #
    # A fresh session per retry is load-bearing: PostgreSQL READ
    # COMMITTED with an open transaction can hold a stale snapshot
    # between SELECTs, so a row that committed mid-retry would not
    # become visible until the transaction restarts.
    for attempt in range(max_retries + 1):
        async with sessionmaker() as session:
            stmt = select(IdempotencyRecord).where(
                IdempotencyRecord.institution_id == ctx.institution_id,
                IdempotencyRecord.idempotency_key == ctx.key,
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if record is None:
                # Race: the row was deleted by the sweep between our
                # failed INSERT and this SELECT. Treat as transient and
                # surface as in_flight so the client retries.
                return ClaimResult(state="in_flight")
            if bytes(record.body_sha256) != ctx.body_sha256:
                raise IdempotencyKeyReuseWithDifferentBody(
                    detail=(
                        "Idempotency-Key was reused within the 24-hour "
                        "window but the request body hash differs from "
                        "the original. Use a fresh Idempotency-Key for "
                        "the new request, or replay the original body "
                        "verbatim."
                    )
                )
            if record.state == "complete":
                # Detach so the caller can access the row outside this
                # session's lifecycle.
                session.expunge(record)
                return ClaimResult(state="replay", record=record)
        # state='processing' — wait briefly and re-read with a fresh
        # session (above ``async with`` block closed when we fell
        # through the if/elif).
        if attempt < max_retries:
            await asyncio.sleep(retry_delay_ms / 1000)

    return ClaimResult(state="in_flight")


async def mark_complete(
    session: AsyncSession,
    ctx: IdempotencyContext,
    *,
    status: int,
    body: dict,
    headers: dict[str, str],
) -> None:
    """UPDATE the placeholder row with the final response payload."""

    stmt = (
        update(IdempotencyRecord)
        .where(
            IdempotencyRecord.institution_id == ctx.institution_id,
            IdempotencyRecord.idempotency_key == ctx.key,
        )
        .values(
            response_status=status,
            response_payload=json.dumps(body, default=str),
            response_headers=json.dumps(headers),
            state="complete",
        )
    )
    await session.execute(stmt)


# ---------------------------------------------------------------------------
# Legacy helpers — retained for backwards-compatibility with the PATCH
# handler, which does not need the concurrent-claim path (PATCH is
# already serialised by the ETag check).
# ---------------------------------------------------------------------------


async def lookup_cached(
    session: AsyncSession, ctx: IdempotencyContext
) -> IdempotencyRecord | None:
    """Return a matching, non-expired record, or None.

    Skips rows still in ``state='processing'`` (returns None so the
    caller proceeds; for PATCH this never collides in practice because
    the ETag check serialises). Raises
    :class:`IdempotencyKeyReuseWithDifferentBody` on body-hash mismatch.
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
    if record.state == "processing":
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
    """Persist a fresh idempotency record (legacy single-INSERT path).

    Used only by the PATCH handler; POST handlers use the
    claim_idempotency_slot / mark_complete pair instead.
    """

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
        state="complete",
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=settings.idempotency_ttl_seconds),
    )
    session.add(record)
    await session.flush()
    return record
