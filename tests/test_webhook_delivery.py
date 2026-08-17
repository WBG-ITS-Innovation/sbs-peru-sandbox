# SPDX-License-Identifier: Apache-2.0
"""Webhook delivery — Workstream D end-to-end against the live testcontainer.

Uses httpx.MockTransport to intercept the outbound POST so the tests
exercise the full sign-and-deliver path without needing a real HTTP
listener. The structlog telemetry assertions cover Workstream F.3's
``webhook.delivery.attempt`` schema since G's smoke depends on it.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


SECRET_HEX = (
    "a1b2c3d4e5f607182930415263748596a1b2c3d4e5f607182930415263748596"  # pragma: allowlist secret
)


async def _seed_webhook(test_database_url: str, *, callback_url: str) -> None:
    engine = create_async_engine(test_database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO institution_webhook_configs "
                "(institution_id, callback_url, enabled, created_at) "
                "VALUES (:iid, :url, true, now()) "
                "ON CONFLICT (institution_id) DO UPDATE "
                "SET callback_url = excluded.callback_url, enabled = true"
            ),
            {"iid": "SBS-001234", "url": callback_url},
        )
        await conn.execute(
            text(
                "INSERT INTO outbound_webhook_secrets "
                "(institution_id, kid, active_secret, rotated_at, created_at) "
                "VALUES (:iid, :kid, decode(:sec, 'hex'), now(), now()) "
                "ON CONFLICT (institution_id) DO UPDATE "
                "SET active_secret = excluded.active_secret, kid = excluded.kid"
            ),
            {"iid": "SBS-001234", "kid": "sandbox-v1", "sec": SECRET_HEX},
        )
    await engine.dispose()


async def _create_batch(test_database_url: str, *, batch_id: str) -> None:
    engine = create_async_engine(test_database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO batches "
                "(batch_id, institution_id, file_name, "
                "reporting_period_start, reporting_period_end, "
                "schema_version, row_count_submitted, "
                "row_count_accepted, row_count_rejected, "
                "sha256, status, completed_at, submitted_at) "
                "VALUES (:bid, 'SBS-001234', :fn, "
                "'2026-05-01', '2026-05-31', 'v0.1.0', "
                ":n, :n, 0, :s, 'complete', now(), now())"
            ),
            {
                "bid": batch_id,
                "fn": f"{batch_id}.csv",
                "n": 3,
                "s": hashlib.sha256(b"placeholder").hexdigest(),
            },
        )
    await engine.dispose()


@pytest.fixture(autouse=True)
def _enable_dev_override(monkeypatch):
    """Bypass URL validation so the test transport URL is accepted."""

    monkeypatch.setenv("SBS_API_ALLOW_INSECURE_WEBHOOK_URLS", "true")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "test")
    from sbs_api.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_delivery_happy_path(test_database_url, client):
    batch_id = "batch_whdtest1happy00000000000000"
    await _seed_webhook(
        test_database_url, callback_url="https://webhook.example.com/sbs-callback"
    )
    await _create_batch(test_database_url, batch_id=batch_id)

    received: list[httpx.Request] = []

    async def _handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(_handler)
    # Patch httpx.AsyncClient to use the mock transport.
    import sbs_api.webhook.delivery as delivery_mod

    real_client_cls = httpx.AsyncClient

    class _Patched(httpx.AsyncClient):
        def __init__(self, **kwargs):
            kwargs["transport"] = transport
            super().__init__(**kwargs)

    delivery_mod.httpx.AsyncClient = _Patched
    try:
        result = await delivery_mod.deliver_webhook_for_batch(
            {"job_try": 1}, batch_id, "batch.complete"
        )
    finally:
        delivery_mod.httpx.AsyncClient = real_client_cls

    assert result["status"] == "delivered"
    assert result["http_status"] == 200
    assert len(received) == 1
    req = received[0]
    # Headers required by ADR 0035.
    assert "X-SBS-Timestamp" in req.headers
    assert req.headers["X-SBS-Key-Id"] == "sandbox-v1"
    assert req.headers["X-SBS-Signature"].startswith("hmac-sha256-v1=")

    # Signature verifies against the same secret.
    from sbs_api.webhook.signing import (
        build_outbound_canonical_request,
        parse_signature_header,
        verify_outbound_signature,
    )

    sig_b64 = parse_signature_header(req.headers["X-SBS-Signature"])
    canonical = build_outbound_canonical_request(
        method="POST",
        callback_path="/sbs-callback",
        timestamp=req.headers["X-SBS-Timestamp"],
        body=req.content,
        institution_id="SBS-001234",
    )
    assert verify_outbound_signature(
        bytes.fromhex(SECRET_HEX), canonical, sig_b64
    ) is True


async def test_delivery_retry_on_500(test_database_url, client):
    batch_id = "batch_whdtest2retry000000000000000"
    await _seed_webhook(
        test_database_url, callback_url="https://webhook.example.com/sbs-callback"
    )
    await _create_batch(test_database_url, batch_id=batch_id)

    attempts: list[int] = [0]

    async def _handler(request: httpx.Request) -> httpx.Response:
        attempts[0] += 1
        return httpx.Response(500, text="oops")

    transport = httpx.MockTransport(_handler)

    import sbs_api.webhook.delivery as delivery_mod

    real_client_cls = httpx.AsyncClient

    class _Patched(httpx.AsyncClient):
        def __init__(self, **kwargs):
            kwargs["transport"] = transport
            super().__init__(**kwargs)

    delivery_mod.httpx.AsyncClient = _Patched
    try:
        from arq.worker import Retry as ArqRetry

        with pytest.raises(ArqRetry) as exc:
            await delivery_mod.deliver_webhook_for_batch(
                {"job_try": 1}, batch_id, "batch.complete"
            )
        # ADR 0035: first retry should wait 30s. arq stores the
        # defer in `defer_score` (milliseconds since now).
        assert exc.value.defer_score == 30_000
    finally:
        delivery_mod.httpx.AsyncClient = real_client_cls

    # The delivery row exists with status=pending and an attempt
    # recorded.
    engine = create_async_engine(test_database_url)
    async with engine.connect() as conn:
        row = await conn.execute(
            text(
                "SELECT status, attempts, next_attempt_at, attempt_history "
                "FROM webhook_deliveries WHERE batch_id = :bid"
            ),
            {"bid": batch_id},
        )
        (status, attempts_n, next_at, history) = row.one()
    await engine.dispose()
    assert status == "pending"
    assert attempts_n == 1
    assert next_at is not None
    history_list = json.loads(history)
    assert history_list[0]["outcome"] == "http_error"
    assert history_list[0]["http_status"] == 500


async def test_delivery_dead_letter_after_max_attempts(
    test_database_url, client
):
    batch_id = "batch_whdtest3deadletter000000000"
    await _seed_webhook(
        test_database_url, callback_url="https://webhook.example.com/sbs-callback"
    )
    await _create_batch(test_database_url, batch_id=batch_id)

    async def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    transport = httpx.MockTransport(_handler)

    import sbs_api.webhook.delivery as delivery_mod

    real_client_cls = httpx.AsyncClient

    class _Patched(httpx.AsyncClient):
        def __init__(self, **kwargs):
            kwargs["transport"] = transport
            super().__init__(**kwargs)

    delivery_mod.httpx.AsyncClient = _Patched
    try:
        # MAX_ATTEMPTS is 6 (5 retries after the initial attempt). On
        # job_try=6 a further failure dead-letters.
        result = await delivery_mod.deliver_webhook_for_batch(
            {"job_try": 6}, batch_id, "batch.complete"
        )
    finally:
        delivery_mod.httpx.AsyncClient = real_client_cls

    assert result["status"] == "delivery_failed"

    engine = create_async_engine(test_database_url)
    async with engine.connect() as conn:
        row = await conn.execute(
            text(
                "SELECT status, attempts, failure_reason "
                "FROM webhook_deliveries WHERE batch_id = :bid"
            ),
            {"bid": batch_id},
        )
        (status, attempts_n, reason) = row.one()
    await engine.dispose()
    assert status == "delivery_failed"
    assert attempts_n == 6
    assert "max attempts exhausted" in (reason or "")


@pytest.mark.parametrize(
    "job_try,expected_defer_seconds",
    [
        (1, 30),
        (2, 120),
        (3, 600),
        (4, 3600),
        (5, 21600),
    ],
)
async def test_delivery_retry_defer_matches_adr_0035_schedule(
    test_database_url, client, job_try, expected_defer_seconds
):
    """ADR 0035 retry schedule: 30s / 2min / 10min / 1hr / 6hr.

    Table-driven across all five retry boundaries. Cross-review
    flagged the absence of the 6hr (job_try=5) test as a gap.
    """

    batch_id = f"batch_whdtable{job_try:02d}000000000000000000"[:35]
    await _seed_webhook(
        test_database_url, callback_url="https://webhook.example.com/sbs-callback"
    )
    await _create_batch(test_database_url, batch_id=batch_id)

    async def _handler(request):
        return httpx.Response(500)

    transport = httpx.MockTransport(_handler)
    import sbs_api.webhook.delivery as delivery_mod

    real_client_cls = httpx.AsyncClient

    class _Patched(httpx.AsyncClient):
        def __init__(self, **kwargs):
            kwargs["transport"] = transport
            super().__init__(**kwargs)

    delivery_mod.httpx.AsyncClient = _Patched
    try:
        from arq.worker import Retry as ArqRetry

        with pytest.raises(ArqRetry) as exc:
            await delivery_mod.deliver_webhook_for_batch(
                {"job_try": job_try}, batch_id, "batch.complete"
            )
        assert exc.value.defer_score == expected_defer_seconds * 1000
    finally:
        delivery_mod.httpx.AsyncClient = real_client_cls


async def test_delivery_url_rejected_no_retry(
    test_database_url, client, monkeypatch
):
    """When the URL fails validation (strict env), the row is dead-lettered."""

    batch_id = "batch_whdtest4urlreject000000000"
    await _seed_webhook(
        test_database_url, callback_url="https://internal.invalid/sbs-callback"
    )
    await _create_batch(test_database_url, batch_id=batch_id)

    # Tighten the env: strict mode, prod-ish env so the override doesn't apply.
    # Done outside the autouse fixture by re-setting.
    monkeypatch.setenv("SBS_API_ALLOW_INSECURE_WEBHOOK_URLS", "false")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "test")
    from sbs_api.config import get_settings

    get_settings.cache_clear()

    import sbs_api.webhook.delivery as delivery_mod

    result = await delivery_mod.deliver_webhook_for_batch(
        {"job_try": 1}, batch_id, "batch.complete"
    )
    assert result["status"] == "delivery_failed"

    engine = create_async_engine(test_database_url)
    async with engine.connect() as conn:
        row = await conn.execute(
            text(
                "SELECT status, failure_reason FROM webhook_deliveries "
                "WHERE batch_id = :bid"
            ),
            {"bid": batch_id},
        )
        (status, reason) = row.one()
    await engine.dispose()
    assert status == "delivery_failed"
    assert "WEBHOOK_URL_REJECTED" in (reason or "")
