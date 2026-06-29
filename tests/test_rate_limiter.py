# SPDX-License-Identifier: Apache-2.0
"""Per-institution business-bucket rate limiter — workstream E.

Tests cover the ADR 0033 contract surface:
- Requests under the limit pass with X-RateLimit-* headers on every
  response (2xx and 429 alike).
- 1001st request to a 1000/min institution returns 429 with
  Retry-After, X-RateLimit-Limit, X-RateLimit-Remaining=0,
  X-RateLimit-Reset.
- Institutions are isolated: large institution's bucket exhaustion
  does not affect a different institution's bucket.
- ``institutions.rate_limit_per_minute`` override takes precedence
  over the tier default.

Limits are deliberately tuned tiny in test (Settings overrides) so the
tests run in milliseconds, not minutes.
"""

from __future__ import annotations

import fakeredis.aioredis
import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from sbs_api.config import get_settings
from sbs_api.db.session import reset_engine_for_test
from sbs_api.dependencies.hmac_verify import (
    override_redis_for_test,
    reset_redis_for_test,
)
from sbs_api.dependencies.mtls import MtlsSubject
from sbs_api.dependencies.rate_limit import business_bucket


@pytest_asyncio.fixture()
async def small_limits_settings(test_database_url, monkeypatch):
    """Tiny limits so tests can exhaust the bucket in 3 requests."""

    monkeypatch.setenv("SBS_API_DATABASE_URL", test_database_url)
    monkeypatch.setenv("SBS_API_MTLS_MODE", "disabled")
    monkeypatch.setenv("SBS_API_DISABLE_MTLS_FOR_TESTS", "true")
    monkeypatch.setenv("SBS_API_AUTH_STUB_ENABLED", "false")
    monkeypatch.setenv("SBS_API_LOG_FORMAT", "json")
    monkeypatch.setenv("SBS_API_OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "test")
    monkeypatch.setenv("SBS_API_IDEMPOTENCY_SWEEP_ENABLED", "false")
    monkeypatch.setenv("SBS_API_RATE_LIMIT_TIER_LARGE_PER_MINUTE", "3")
    monkeypatch.setenv("SBS_API_RATE_LIMIT_TIER_SMALL_PER_MINUTE", "2")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest_asyncio.fixture()
async def fake_redis():
    client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    override_redis_for_test(client)
    yield client
    await client.aclose()
    reset_redis_for_test()


async def _set_override(test_database_url: str, institution_id: str, value: int | None) -> None:
    engine = create_async_engine(test_database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE institutions SET rate_limit_per_minute = :v "
                "WHERE institution_id = :iid"
            ),
            {"v": value, "iid": institution_id},
        )
    await engine.dispose()


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/v1/probe")
    async def probe(subject: MtlsSubject = Depends(business_bucket)) -> dict:
        return {"institution_id": subject.institution_id}

    from sbs_api.errors.handlers import install_exception_handlers

    install_exception_handlers(app)
    return app


@pytest.mark.asyncio
async def test_under_limit_passes_with_headers(
    small_limits_settings, db_schema, fake_redis
):
    """Three requests succeed (limit=3 large); each carries X-RateLimit-*."""

    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        for expected_remaining in (2, 1, 0):
            resp = await ac.get("/v1/probe")
            assert resp.status_code == 200, resp.text
            assert resp.headers["X-RateLimit-Limit"] == "3"
            assert resp.headers["X-RateLimit-Remaining"] == str(expected_remaining)
            assert int(resp.headers["X-RateLimit-Reset"]) > 0


@pytest.mark.asyncio
async def test_over_limit_returns_429_with_all_four_headers(
    small_limits_settings, db_schema, fake_redis
):
    """The 4th request to a 3/min institution returns 429 with the four
    rate-limit headers on the ProblemDetail response."""

    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        for _ in range(3):
            await ac.get("/v1/probe")
        resp = await ac.get("/v1/probe")

    assert resp.status_code == 429
    body = resp.json()
    assert body["code"] == "SBS-429-001"
    assert body["type"].endswith("/RATE_LIMIT_EXCEEDED")

    # All four headers must be present on the 429.
    assert resp.headers["X-RateLimit-Limit"] == "3"
    assert resp.headers["X-RateLimit-Remaining"] == "0"
    assert int(resp.headers["X-RateLimit-Reset"]) > 0
    retry_after = int(resp.headers["Retry-After"])
    assert retry_after >= 1


@pytest.mark.asyncio
async def test_institutions_are_isolated(
    small_limits_settings, db_schema, fake_redis, test_database_url
):
    """SBS-001234 exhausting its bucket must not affect SBS-005678.

    The mTLS bypass returns SBS-001234. To exercise the second
    institution we override the dependency to return a different
    subject.
    """

    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)

    # First: drain SBS-001234 (large tier, limit=3).
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        for _ in range(3):
            r = await ac.get("/v1/probe")
            assert r.status_code == 200
        over = await ac.get("/v1/probe")
        assert over.status_code == 429

    # Now override the mTLS dependency to return SBS-005678 (small tier,
    # limit=2). The bucket key differs so it has a fresh allowance.
    from sbs_api.dependencies.mtls import verified_mtls_subject

    async def coopac_subject() -> MtlsSubject:
        return MtlsSubject(
            institution_id="SBS-005678",
            cn="COOPAC_DEMO_002",
            cert_thumbprint="0" * 64,
        )

    app.dependency_overrides[verified_mtls_subject] = coopac_subject

    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        for expected_remaining in (1, 0):
            r = await ac.get("/v1/probe")
            assert r.status_code == 200, r.text
            assert r.headers["X-RateLimit-Limit"] == "2"
            assert r.headers["X-RateLimit-Remaining"] == str(expected_remaining)
        over = await ac.get("/v1/probe")
        assert over.status_code == 429


@pytest.mark.asyncio
async def test_per_institution_override_beats_tier_default(
    small_limits_settings, db_schema, fake_redis, test_database_url
):
    """institutions.rate_limit_per_minute, when non-NULL, wins over tier."""

    # BANCO (large tier, settings default 3) gets an override of 1.
    await _set_override(test_database_url, "SBS-001234", 1)
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        first = await ac.get("/v1/probe")
        assert first.status_code == 200
        assert first.headers["X-RateLimit-Limit"] == "1"
        assert first.headers["X-RateLimit-Remaining"] == "0"
        second = await ac.get("/v1/probe")
        assert second.status_code == 429
        assert second.headers["X-RateLimit-Limit"] == "1"


@pytest.mark.asyncio
async def test_small_tier_uses_small_default(
    small_limits_settings, db_schema, fake_redis, test_database_url
):
    """Switch the bypass-target institution to small tier; ensure limit=2."""

    # Make BANCO 'small' so the bypass institution_id picks small default.
    engine = create_async_engine(test_database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE institutions SET tier_classification='small' "
                "WHERE institution_id='SBS-001234'"
            )
        )
    await engine.dispose()
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        for expected_remaining in (1, 0):
            r = await ac.get("/v1/probe")
            assert r.status_code == 200
            assert r.headers["X-RateLimit-Limit"] == "2"
            assert r.headers["X-RateLimit-Remaining"] == str(expected_remaining)
        over = await ac.get("/v1/probe")
        assert over.status_code == 429
