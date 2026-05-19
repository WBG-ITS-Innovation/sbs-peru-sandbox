"""JWT shape and claims for tokens issued by /v1/oauth/token — workstream C.

Asserts the contract surface SDK consumers see: kid in the header from
day one (pressure-test amendment to ADR 0032), the seven canonical
claims including cnf.x5t#S256, and the 900-second TTL.
"""

from __future__ import annotations

import base64
import json

import fakeredis.aioredis
import jwt
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

# The mTLS bypass returns this fixed thumbprint; the JWT must echo it
# in cnf.x5t#S256.
BYPASS_THUMBPRINT = "0" * 64


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
    monkeypatch.setenv("SBS_API_RATE_LIMIT_TOKEN_ENDPOINT_PER_MINUTE", "10000")
    get_settings.cache_clear()
    override_signing_key_for_test(TEST_KEY)
    yield get_settings()
    reset_signing_key_for_test()
    get_settings.cache_clear()


@pytest_asyncio.fixture(autouse=True)
async def _fake_redis_for_claims_tests():
    client = fakeredis.aioredis.FakeRedis(decode_responses=False)
    override_redis_for_test(client)
    yield client
    await client.aclose()
    reset_redis_for_test()


async def _seed(test_database_url: str) -> None:
    h = hash_client_secret(BANCO_SECRET)
    engine = create_async_engine(test_database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE institutions SET permitted_scopes = ARRAY['complaints:write','complaints:read','batch:upload','status:read']::varchar[] WHERE institution_id = :iid"
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


def _decode_header_b64(token: str) -> dict:
    header_segment = token.split(".")[0]
    padded = header_segment + "=" * (-len(header_segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


@pytest.mark.asyncio
async def test_jwt_header_carries_kid_from_day_one(
    oauth_settings, db_schema, test_database_url
):
    await _seed(test_database_url)
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/oauth/token",
            data={"grant_type": "client_credentials", "scope": "complaints:write"},
            headers={"authorization": _basic_auth(BANCO_CLIENT, BANCO_SECRET)},
        )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    header = _decode_header_b64(token)
    assert header["alg"] == "HS256"
    assert header["kid"] == "sandbox-v1"
    assert header["typ"] == "JWT"


@pytest.mark.asyncio
async def test_jwt_claims_required_fields(
    oauth_settings, db_schema, test_database_url
):
    await _seed(test_database_url)
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/oauth/token",
            data={
                "grant_type": "client_credentials",
                "scope": "complaints:write batch:upload",
            },
            headers={"authorization": _basic_auth(BANCO_CLIENT, BANCO_SECRET)},
        )
    token = resp.json()["access_token"]
    decoded = jwt.decode(
        token,
        TEST_KEY,
        algorithms=["HS256"],
        audience="sbs-api",
        issuer="https://sbs-suptech-sandbox.local",
    )
    assert decoded["sub"] == BANCO_ID
    assert decoded["aud"] == "sbs-api"
    assert decoded["iss"] == "https://sbs-suptech-sandbox.local"
    assert decoded["exp"] - decoded["iat"] == 900
    assert set(decoded["scope"].split()) == {"complaints:write", "batch:upload"}
    assert "cnf" in decoded
    assert decoded["cnf"]["x5t#S256"] == BYPASS_THUMBPRINT


@pytest.mark.asyncio
async def test_jwt_unsigned_alg_rejected_on_verify(
    oauth_settings, db_schema, test_database_url
):
    """A token forged with alg=none must be rejected by verify_token.

    Defence against the classical 'alg confusion' attack: even if a
    client crafted a token with alg=none, the verifier accepts only
    HS256.
    """

    from sbs_api.auth.oauth import TokenVerificationError, verify_token

    forged = jwt.encode(
        {
            "iss": "https://sbs-suptech-sandbox.local",
            "aud": "sbs-api",
            "iat": 0,
            "exp": 9999999999,
            "sub": BANCO_ID,
            "scope": "complaints:write",
            "cnf": {"x5t#S256": BYPASS_THUMBPRINT},
        },
        "",
        algorithm="none",
    )
    with pytest.raises(TokenVerificationError):
        verify_token(forged, key=TEST_KEY, accepted_algs=("HS256",))


@pytest.mark.asyncio
async def test_jwt_wrong_algorithm_rejected(
    oauth_settings, db_schema, test_database_url
):
    """A token signed with HS384 must be rejected when only HS256 is accepted."""

    from sbs_api.auth.oauth import TokenVerificationError, verify_token

    forged = jwt.encode(
        {
            "iss": "https://sbs-suptech-sandbox.local",
            "aud": "sbs-api",
            "iat": 0,
            "exp": 9999999999,
            "sub": BANCO_ID,
            "scope": "complaints:write",
            "cnf": {"x5t#S256": BYPASS_THUMBPRINT},
        },
        TEST_KEY,
        algorithm="HS384",
    )
    with pytest.raises(TokenVerificationError):
        verify_token(forged, key=TEST_KEY, accepted_algs=("HS256",))
