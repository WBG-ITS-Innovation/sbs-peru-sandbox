# SPDX-License-Identifier: Apache-2.0
"""Token-endpoint bucket — workstream E (ADR 0033 pressure-test amendment).

POST /v1/oauth/token has its own bucket, keyed on mTLS CN. The default
is 50 req/min; tests reduce it to 2 for fast feedback. The bucket is
independent of the business bucket: exhausting the token endpoint must
NOT consume any business-bucket budget, and vice versa.
"""

from __future__ import annotations

import base64

import fakeredis.aioredis
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from sbs_api.auth.oauth import hash_client_secret
from sbs_api.config import get_settings
from sbs_api.db.session import reset_engine_for_test
from sbs_api.dependencies.hmac_verify import (
    override_redis_for_test,
    reset_redis_for_test,
)
from sbs_api.dependencies.oauth import (
    override_signing_key_for_test,
    reset_signing_key_for_test,
)
from sbs_api.routes.oauth import router as oauth_router

BANCO_ID = "SBS-001234"
BANCO_CLIENT = "banco-demo-001"
BANCO_SECRET = "banco-demo-001-secret"  # pragma: allowlist secret
TEST_KEY = b"\x42" * 32


@pytest_asyncio.fixture()
async def tiny_token_bucket(test_database_url, monkeypatch):
    """Token-endpoint limit set to 2/min for fast exhaustion."""

    monkeypatch.setenv("SBS_API_DATABASE_URL", test_database_url)
    monkeypatch.setenv("SBS_API_MTLS_MODE", "disabled")
    monkeypatch.setenv("SBS_API_DISABLE_MTLS_FOR_TESTS", "true")
    monkeypatch.setenv("SBS_API_AUTH_STUB_ENABLED", "false")
    monkeypatch.setenv("SBS_API_LOG_FORMAT", "json")
    monkeypatch.setenv("SBS_API_OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "test")
    monkeypatch.setenv("SBS_API_IDEMPOTENCY_SWEEP_ENABLED", "false")
    monkeypatch.setenv("SBS_API_RATE_LIMIT_TOKEN_ENDPOINT_PER_MINUTE", "2")
    # Make business bucket comparatively generous so it doesn't
    # interfere with token-endpoint accounting in the cross-bucket test.
    monkeypatch.setenv("SBS_API_RATE_LIMIT_TIER_LARGE_PER_MINUTE", "1000")
    get_settings.cache_clear()
    override_signing_key_for_test(TEST_KEY)
    yield get_settings()
    reset_signing_key_for_test()
    get_settings.cache_clear()


@pytest_asyncio.fixture()
async def fake_redis():
    client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    override_redis_for_test(client)
    yield client
    await client.aclose()
    reset_redis_for_test()


async def _seed_oauth_client(test_database_url: str) -> None:
    h = hash_client_secret(BANCO_SECRET)
    engine = create_async_engine(test_database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE institutions SET permitted_scopes = "
                "ARRAY['complaints:write','complaints:read','batch:upload']::varchar[] "
                "WHERE institution_id = :iid"
            ),
            {"iid": BANCO_ID},
        )
        await conn.execute(
            text(
                "INSERT INTO oauth_clients (client_id, institution_id, client_secret_hash, cert_thumbprint_required, created_at) "
                "VALUES (:cid, :iid, :h, NULL, now()) "
                "ON CONFLICT (client_id) DO UPDATE SET client_secret_hash = excluded.client_secret_hash"
            ),
            {"cid": BANCO_CLIENT, "iid": BANCO_ID, "h": h},
        )
    await engine.dispose()


def _basic_auth(cid: str, sec: str) -> str:
    return "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode("ascii")


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(oauth_router, prefix="/v1")
    from sbs_api.errors.handlers import install_exception_handlers

    install_exception_handlers(app)
    return app


@pytest.mark.asyncio
async def test_token_endpoint_under_limit(
    tiny_token_bucket, db_schema, fake_redis, test_database_url
):
    """2 token requests succeed with X-RateLimit-* headers carrying limit=2."""

    await _seed_oauth_client(test_database_url)
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        for expected_remaining in (1, 0):
            resp = await ac.post(
                "/v1/oauth/token",
                data={"grant_type": "client_credentials", "scope": "complaints:write"},
                headers={"authorization": _basic_auth(BANCO_CLIENT, BANCO_SECRET)},
            )
            assert resp.status_code == 200, resp.text
            assert resp.headers["X-RateLimit-Limit"] == "2"
            assert resp.headers["X-RateLimit-Remaining"] == str(expected_remaining)


@pytest.mark.asyncio
async def test_token_endpoint_over_limit_returns_429(
    tiny_token_bucket, db_schema, fake_redis, test_database_url
):
    """The 3rd call to a 2/min token endpoint returns 429 with the
    distinct ``TOKEN_ENDPOINT_RATE_LIMIT_EXCEEDED`` code (not the
    business code)."""

    await _seed_oauth_client(test_database_url)
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        for _ in range(2):
            await ac.post(
                "/v1/oauth/token",
                data={"grant_type": "client_credentials"},
                headers={"authorization": _basic_auth(BANCO_CLIENT, BANCO_SECRET)},
            )
        resp = await ac.post(
            "/v1/oauth/token",
            data={"grant_type": "client_credentials"},
            headers={"authorization": _basic_auth(BANCO_CLIENT, BANCO_SECRET)},
        )

    assert resp.status_code == 429
    body = resp.json()
    assert body["code"] == "SBS-429-002"
    assert body["type"].endswith("/TOKEN_ENDPOINT_RATE_LIMIT_EXCEEDED")
    assert resp.headers["X-RateLimit-Limit"] == "2"
    assert resp.headers["X-RateLimit-Remaining"] == "0"
    assert int(resp.headers["X-RateLimit-Reset"]) > 0
    assert int(resp.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_token_bucket_is_keyed_on_cn_not_institution_id(
    tiny_token_bucket, db_schema, fake_redis, test_database_url
):
    """Different mTLS CNs must have independent buckets even when the
    same institution_id is reached by both.

    The mTLS bypass returns a fixed CN=BANCO_DEMO_001. We override the
    dependency to vary the CN while keeping institution_id constant,
    which is the regulatory scenario: one institution has two issued
    certs (during cert rotation), and each cert gets its own token
    endpoint budget.
    """

    await _seed_oauth_client(test_database_url)
    await reset_engine_for_test()

    from sbs_api.dependencies.mtls import MtlsSubject, verified_mtls_subject

    app = _make_app()

    # Drain CN=BANCO_DEMO_001 (the default bypass).
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        for _ in range(2):
            await ac.post(
                "/v1/oauth/token",
                data={"grant_type": "client_credentials"},
                headers={"authorization": _basic_auth(BANCO_CLIENT, BANCO_SECRET)},
            )
        third = await ac.post(
            "/v1/oauth/token",
            data={"grant_type": "client_credentials"},
            headers={"authorization": _basic_auth(BANCO_CLIENT, BANCO_SECRET)},
        )
        assert third.status_code == 429  # bucket A drained

    # Override CN to a fresh value. institution_id stays the same.
    async def fresh_cn() -> MtlsSubject:
        return MtlsSubject(
            institution_id=BANCO_ID,
            cn="BANCO_DEMO_001_NEWCERT",
            cert_thumbprint="0" * 64,
        )

    app.dependency_overrides[verified_mtls_subject] = fresh_cn

    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/oauth/token",
            data={"grant_type": "client_credentials"},
            headers={"authorization": _basic_auth(BANCO_CLIENT, BANCO_SECRET)},
        )
    # Fresh CN bucket has full allowance.
    assert resp.status_code == 200, resp.text
    assert resp.headers["X-RateLimit-Limit"] == "2"
    assert resp.headers["X-RateLimit-Remaining"] == "1"
