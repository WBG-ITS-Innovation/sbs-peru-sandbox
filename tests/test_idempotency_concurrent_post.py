# SPDX-License-Identifier: Apache-2.0
"""Concurrent-POST idempotency policy — ADR 0029 amendment, workstream F.1.

The placeholder-INSERT-under-unique-constraint pattern lands in F.1.
Tests pin the three reachable states:
* fresh claim — INSERT succeeds, route proceeds
* replay (state='complete') — second call returns the cached response
* in-flight (state='processing') — second call retries 50ms × 3, then
  409 IDEMPOTENCY_KEY_IN_FLIGHT
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.config import get_settings
from sbs_api.db.models.idempotency import IdempotencyRecord
from sbs_api.db.session import reset_engine_for_test
from sbs_api.dependencies.idempotency import (
    ClaimResult,
    claim_idempotency_slot,
    get_idempotency_context,
    mark_complete,
)
from sbs_api.errors.exceptions import IdempotencyKeyReuseWithDifferentBody


@pytest_asyncio.fixture()
async def idem_settings(test_database_url, monkeypatch):
    monkeypatch.setenv("SBS_API_DATABASE_URL", test_database_url)
    monkeypatch.setenv("SBS_API_AUTH_STUB_ENABLED", "true")
    monkeypatch.setenv("SBS_API_LOG_FORMAT", "json")
    monkeypatch.setenv("SBS_API_OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "test")
    monkeypatch.setenv("SBS_API_IDEMPOTENCY_SWEEP_ENABLED", "false")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


def _ctx(institution_id: str = "SBS-001234", key: str = "concurrent-post-test"):
    return get_idempotency_context(
        institution_id=institution_id,
        key=key,
        body=b'{"hello":"world"}',
        method="POST",
        path="/v1/complaints",
    )


@pytest.mark.asyncio
async def test_first_call_claims_fresh_slot(
    idem_settings, db_schema, test_database_url
):
    await reset_engine_for_test()
    engine = create_async_engine(test_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    result = await claim_idempotency_slot(sessionmaker, _ctx())
    assert result.state == "claimed"
    assert result.record is None

    # The placeholder row exists with state='processing'.
    async with sessionmaker() as session:
        rows = (await session.execute(select(IdempotencyRecord))).scalars().all()
    assert len(rows) == 1
    assert rows[0].state == "processing"
    assert rows[0].response_status == 0  # placeholder

    await engine.dispose()


@pytest.mark.asyncio
async def test_replay_after_completion_returns_cached(
    idem_settings, db_schema, test_database_url
):
    await reset_engine_for_test()
    engine = create_async_engine(test_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    ctx = _ctx()

    # First call: claim + mark complete.
    first = await claim_idempotency_slot(sessionmaker, ctx)
    assert first.state == "claimed"

    async with sessionmaker() as session:
        async with session.begin():
            await mark_complete(
                session,
                ctx,
                status=201,
                body={"complaint_id": "CMP-2026-0001"},
                headers={"Location": "/v1/complaints/CMP-2026-0001"},
            )

    # Second call with the same Idempotency-Key + same body.
    second = await claim_idempotency_slot(sessionmaker, ctx)
    assert second.state == "replay"
    assert second.record is not None
    assert second.record.response_status == 201
    assert '"complaint_id"' in second.record.response_payload

    await engine.dispose()


@pytest.mark.asyncio
async def test_second_call_during_processing_returns_in_flight(
    idem_settings, db_schema, test_database_url, monkeypatch
):
    """A concurrent second call against an in-progress row exhausts the
    50ms × 3 retry window and returns ``state='in_flight'``.

    The first call's placeholder is committed by claim_idempotency_slot,
    and we intentionally do NOT call mark_complete before the second
    call runs. After 3 retries the second call gives up.
    """

    await reset_engine_for_test()
    engine = create_async_engine(test_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    ctx = _ctx()

    first = await claim_idempotency_slot(sessionmaker, ctx)
    assert first.state == "claimed"

    # Tighten the retry to keep the test fast.
    second = await claim_idempotency_slot(
        sessionmaker, ctx, retry_delay_ms=10, max_retries=2
    )
    assert second.state == "in_flight"

    await engine.dispose()


@pytest.mark.asyncio
async def test_second_call_observes_completion_within_window(
    idem_settings, db_schema, test_database_url
):
    """If the first call completes within the second's retry window,
    the second sees state='complete' and returns the cached response.
    """

    await reset_engine_for_test()
    engine = create_async_engine(test_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    ctx = _ctx()

    first = await claim_idempotency_slot(sessionmaker, ctx)
    assert first.state == "claimed"

    async def _complete_after(delay_s: float) -> None:
        await asyncio.sleep(delay_s)
        async with sessionmaker() as session:
            async with session.begin():
                await mark_complete(
                    session, ctx, status=201, body={"ok": True}, headers={}
                )

    # Schedule completion at ~30ms; the second call has a 4 × 50ms
    # retry budget (200ms total).
    completion_task = asyncio.create_task(_complete_after(0.03))

    second = await claim_idempotency_slot(
        sessionmaker, ctx, retry_delay_ms=50, max_retries=4
    )
    await completion_task

    assert second.state == "replay"
    assert second.record is not None
    assert second.record.response_status == 201

    await engine.dispose()


@pytest.mark.asyncio
async def test_different_body_rejected_during_replay(
    idem_settings, db_schema, test_database_url
):
    """Same Idempotency-Key, different body → 409 body-hash mismatch
    (not 409 in-flight)."""

    await reset_engine_for_test()
    engine = create_async_engine(test_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    first_ctx = _ctx()
    second_ctx = get_idempotency_context(
        institution_id="SBS-001234",
        key="concurrent-post-test",  # same key as first_ctx
        body=b'{"different":"body"}',  # but different body
        method="POST",
        path="/v1/complaints",
    )

    first = await claim_idempotency_slot(sessionmaker, first_ctx)
    assert first.state == "claimed"
    async with sessionmaker() as session:
        async with session.begin():
            await mark_complete(
                session, first_ctx, status=201, body={"ok": True}, headers={}
            )

    with pytest.raises(IdempotencyKeyReuseWithDifferentBody):
        await claim_idempotency_slot(sessionmaker, second_ctx)

    await engine.dispose()


@pytest.mark.asyncio
async def test_isolated_institutions_have_independent_slots(
    idem_settings, db_schema, test_database_url
):
    """Same Idempotency-Key value across two different institutions
    must not collide — the unique constraint is on
    (institution_id, idempotency_key)."""

    await reset_engine_for_test()
    engine = create_async_engine(test_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    banco_ctx = _ctx(institution_id="SBS-001234", key="shared-key")
    coopac_ctx = _ctx(institution_id="SBS-005678", key="shared-key")

    banco = await claim_idempotency_slot(sessionmaker, banco_ctx)
    coopac = await claim_idempotency_slot(sessionmaker, coopac_ctx)
    assert banco.state == "claimed"
    assert coopac.state == "claimed"

    await engine.dispose()
