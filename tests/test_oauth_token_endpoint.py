"""POST /v1/oauth/token endpoint tests — workstream C.

Exercises the happy path plus every RFC 6749 §5.2 error code path the
endpoint declares: invalid_request, invalid_grant, invalid_scope.
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
COOPAC_ID = "SBS-005678"
BANCO_CLIENT = "banco-demo-001"
BANCO_SECRET = "banco-demo-001-secret"  # pragma: allowlist secret
COOPAC_CLIENT = "coopac-demo-002"
COOPAC_SECRET = "coopac-demo-002-secret"  # pragma: allowlist secret
TEST_KEY = b"\x42" * 32


@pytest_asyncio.fixture()
async def oauth_settings(test_database_url, monkeypatch):
    monkeypatch.setenv("SBS_API_DATABASE_URL", test_database_url)
    monkeypatch.setenv("SBS_API_MTLS_MODE", "disabled")
    monkeypatch.setenv("SBS_API_DISABLE_MTLS_FOR_TESTS", "true")
    monkeypatch.setenv("SBS_API_AUTH_STUB_ENABLED", "false")
    monkeypatch.setenv("SBS_API_LOG_FORMAT", "json")
    monkeypatch.setenv("SBS_API_OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "test")
    monkeypatch.setenv("SBS_API_IDEMPOTENCY_SWEEP_ENABLED", "false")
    # Token endpoint bucket is generous so the OAuth tests can fire
    # many requests without hitting it — the bucket itself is exercised
    # in test_rate_limiter_token_endpoint.py.
    monkeypatch.setenv("SBS_API_RATE_LIMIT_TOKEN_ENDPOINT_PER_MINUTE", "10000")
    get_settings.cache_clear()
    override_signing_key_for_test(TEST_KEY)
    yield get_settings()
    reset_signing_key_for_test()
    get_settings.cache_clear()


@pytest_asyncio.fixture(autouse=True)
async def _fake_redis_for_oauth_endpoint_tests():
    """Auto-inject fakeredis so the token-endpoint bucket has a backing."""

    client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    override_redis_for_test(client)
    yield client
    await client.aclose()
    reset_redis_for_test()


async def _seed_clients(
    test_database_url: str,
    *,
    permitted_scopes: dict[str, list[str]] | None = None,
) -> None:
    """Insert the two demo oauth_clients rows."""

    scopes = permitted_scopes or {
        BANCO_ID: ["complaints:write", "complaints:read", "batch:upload"],
        COOPAC_ID: ["complaints:write", "complaints:read"],
    }
    banco_hash = hash_client_secret(BANCO_SECRET)
    coopac_hash = hash_client_secret(COOPAC_SECRET)
    engine = create_async_engine(test_database_url)
    async with engine.begin() as conn:
        # Update permitted_scopes on institutions for both demo rows.
        for iid, scope_list in scopes.items():
            await conn.execute(
                text(
                    "UPDATE institutions SET permitted_scopes = :scopes "
                    "WHERE institution_id = :iid"
                ),
                {"scopes": scope_list, "iid": iid},
            )
        await conn.execute(
            text(
                "INSERT INTO oauth_clients "
                "(client_id, institution_id, client_secret_hash, cert_thumbprint_required, created_at) "
                "VALUES (:cid, :iid, :hash, NULL, now()) "
                "ON CONFLICT (client_id) DO UPDATE SET "
                "client_secret_hash = excluded.client_secret_hash"
            ),
            {"cid": BANCO_CLIENT, "iid": BANCO_ID, "hash": banco_hash},
        )
        await conn.execute(
            text(
                "INSERT INTO oauth_clients "
                "(client_id, institution_id, client_secret_hash, cert_thumbprint_required, created_at) "
                "VALUES (:cid, :iid, :hash, NULL, now()) "
                "ON CONFLICT (client_id) DO UPDATE SET "
                "client_secret_hash = excluded.client_secret_hash"
            ),
            {"cid": COOPAC_CLIENT, "iid": COOPAC_ID, "hash": coopac_hash},
        )
    await engine.dispose()


def _basic_auth(client_id: str, client_secret: str) -> str:
    return (
        "Basic "
        + base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    )


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(oauth_router, prefix="/v1")

    from sbs_api.errors.handlers import install_exception_handlers

    install_exception_handlers(app)
    return app


@pytest.mark.asyncio
async def test_token_endpoint_happy_path(oauth_settings, db_schema, test_database_url):
    await _seed_clients(test_database_url)
    await reset_engine_for_test()

    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/oauth/token",
            data={
                "grant_type": "client_credentials",
                "scope": "complaints:write complaints:read",
            },
            headers={"authorization": _basic_auth(BANCO_CLIENT, BANCO_SECRET)},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 900
    assert set(body["scope"].split()) == {"complaints:write", "complaints:read"}
    assert body["access_token"].count(".") == 2  # header.payload.signature


@pytest.mark.asyncio
async def test_unsupported_grant_type(oauth_settings, db_schema, test_database_url):
    await _seed_clients(test_database_url)
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/oauth/token",
            data={"grant_type": "authorization_code"},
            headers={"authorization": _basic_auth(BANCO_CLIENT, BANCO_SECRET)},
        )
    body = resp.json()
    assert resp.status_code == 400
    assert body["code"] == "SBS-400-011"
    assert body["type"].endswith("/INVALID_REQUEST")


@pytest.mark.asyncio
async def test_invalid_client_secret(oauth_settings, db_schema, test_database_url):
    await _seed_clients(test_database_url)
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/oauth/token",
            data={"grant_type": "client_credentials"},
            headers={"authorization": _basic_auth(BANCO_CLIENT, "wrong-secret")},
        )
    body = resp.json()
    assert resp.status_code == 401
    assert body["code"] == "SBS-401-025"
    assert body["type"].endswith("/INVALID_GRANT")


@pytest.mark.asyncio
async def test_unknown_client_id(oauth_settings, db_schema, test_database_url):
    await _seed_clients(test_database_url)
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/oauth/token",
            data={"grant_type": "client_credentials"},
            headers={"authorization": _basic_auth("not-a-real-client", "x")},
        )
    body = resp.json()
    assert body["code"] == "SBS-401-025"
    assert body["type"].endswith("/INVALID_GRANT")


@pytest.mark.asyncio
async def test_client_belongs_to_other_institution(
    oauth_settings, db_schema, test_database_url
):
    """The mTLS bypass sentinel returns institution_id=SBS-001234; using
    COOPAC's client_id (which belongs to SBS-005678) must fail."""

    await _seed_clients(test_database_url)
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/oauth/token",
            data={"grant_type": "client_credentials"},
            headers={"authorization": _basic_auth(COOPAC_CLIENT, COOPAC_SECRET)},
        )
    body = resp.json()
    assert resp.status_code == 401
    assert body["code"] == "SBS-401-025"
    assert body["type"].endswith("/INVALID_GRANT")


@pytest.mark.asyncio
async def test_invalid_scope_unknown_value(oauth_settings, db_schema, test_database_url):
    await _seed_clients(test_database_url)
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/oauth/token",
            data={
                "grant_type": "client_credentials",
                "scope": "does:not:exist",
            },
            headers={"authorization": _basic_auth(BANCO_CLIENT, BANCO_SECRET)},
        )
    body = resp.json()
    assert resp.status_code == 400
    assert body["code"] == "SBS-400-010"
    assert body["type"].endswith("/INVALID_SCOPE")


@pytest.mark.asyncio
async def test_invalid_scope_empty_intersection(
    oauth_settings, db_schema, test_database_url
):
    # Banco's institution row only permits 'batch:upload' for this test.
    await _seed_clients(
        test_database_url,
        permitted_scopes={
            BANCO_ID: ["batch:upload"],
            COOPAC_ID: ["complaints:read"],
        },
    )
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/oauth/token",
            data={
                "grant_type": "client_credentials",
                "scope": "complaints:write",
            },
            headers={"authorization": _basic_auth(BANCO_CLIENT, BANCO_SECRET)},
        )
    body = resp.json()
    assert resp.status_code == 400
    assert body["code"] == "SBS-400-010"
    assert body["type"].endswith("/INVALID_SCOPE")


@pytest.mark.asyncio
async def test_missing_authorization_header(oauth_settings, db_schema, test_database_url):
    await _seed_clients(test_database_url)
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/oauth/token",
            data={"grant_type": "client_credentials"},
        )
    body = resp.json()
    assert resp.status_code == 400
    assert body["code"] == "SBS-400-011"
    assert body["type"].endswith("/INVALID_REQUEST")
