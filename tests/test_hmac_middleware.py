# SPDX-License-Identifier: Apache-2.0
"""HMAC verification dependency end-to-end tests — workstream B.

Spins up a minimal FastAPI app with a route depending on
:func:`verified_hmac_signature` (which transitively depends on
:func:`verified_mtls_subject`). Uses fakeredis for the replay cache so
no Redis container is required.

Tests pin every error code path enumerated in ADR 0027 amendment:
SIGNATURE_MISSING_HEADER, SIGNATURE_ALGORITHM_UNSUPPORTED,
SIGNATURE_INVALID, SIGNATURE_EXPIRED, SIGNATURE_REPLAYED,
SIGNATURE_INSTITUTION_MISMATCH.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac as _hmac
import secrets

import fakeredis.aioredis
import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from sbs_api.auth.hmac import (
    build_canonical_request,
    compute_signature,
)
from sbs_api.config import get_settings
from sbs_api.db.session import reset_engine_for_test
from sbs_api.dependencies.hmac_verify import (
    override_redis_for_test,
    reset_redis_for_test,
    verified_hmac_signature,
)
from sbs_api.dependencies.mtls import MtlsSubject

DEMO_SECRET = bytes.fromhex(
    "4a5f1d2e8c7b9a3e5f2d1c8b9a3e5f2d4a5f1d2e8c7b9a3e5f2d1c8b9a3e5f2d"  # pragma: allowlist secret
)
DEMO_INSTITUTION = "SBS-001234"
DEMO_CN = "BANCO_DEMO_001"


@pytest_asyncio.fixture()
async def hmac_settings(test_database_url, monkeypatch):
    monkeypatch.setenv("SBS_API_DATABASE_URL", test_database_url)
    monkeypatch.setenv("SBS_API_MTLS_MODE", "disabled")
    monkeypatch.setenv("SBS_API_DISABLE_MTLS_FOR_TESTS", "true")
    monkeypatch.setenv("SBS_API_AUTH_STUB_ENABLED", "false")
    monkeypatch.setenv("SBS_API_LOG_FORMAT", "json")
    monkeypatch.setenv("SBS_API_OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "test")
    monkeypatch.setenv("SBS_API_REDIS_URL", "redis://localhost-fake/0")
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


async def _seed_secrets(
    test_database_url: str,
    *,
    institution_id: str = DEMO_INSTITUTION,
    active: bytes = DEMO_SECRET,
    previous: bytes | None = None,
    previous_retires_at: dt.datetime | None = None,
) -> None:
    engine = create_async_engine(test_database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO institution_secrets "
                "(institution_id, active_secret, previous_secret, "
                "previous_secret_retires_at, rotated_at, created_at) "
                "VALUES (:iid, :act, :prev, :prev_ret, now(), now()) "
                "ON CONFLICT (institution_id) DO UPDATE SET "
                "active_secret = excluded.active_secret, "
                "previous_secret = excluded.previous_secret, "
                "previous_secret_retires_at = excluded.previous_secret_retires_at"
            ),
            {
                "iid": institution_id,
                "act": active,
                "prev": previous,
                "prev_ret": previous_retires_at,
            },
        )
    await engine.dispose()


def _make_app() -> FastAPI:
    """Build an app with a route depending on verified_hmac_signature.

    The mTLS dependency is bypassed by SBS_API_DISABLE_MTLS_FOR_TESTS=true;
    the HMAC dependency still runs against the demo institution
    (SBS-001234) returned by the bypass sentinel.
    """

    app = FastAPI()

    @app.post("/v1/echo")
    async def echo(
        subject: MtlsSubject = Depends(verified_hmac_signature),
    ) -> dict:
        return {"institution_id": subject.institution_id, "cn": subject.cn}

    from sbs_api.errors.handlers import install_exception_handlers

    install_exception_handlers(app)
    return app


def _sign_request(
    *,
    method: str,
    target: str,
    host: str,
    timestamp: str,
    body: bytes,
    institution_id: str,
    secret: bytes,
) -> str:
    canonical = build_canonical_request(
        method=method,
        target=target,
        host=host,
        timestamp=timestamp,
        body=body,
        institution_id=institution_id,
    )
    sig = compute_signature(secret, canonical)
    return f"hmac-sha256-v1={sig}"


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.mark.asyncio
async def test_valid_signature_passes(
    hmac_settings, db_schema, fake_redis, test_database_url
):
    await _seed_secrets(test_database_url)
    await reset_engine_for_test()
    app = _make_app()

    body = b'{"client_submission_id":"X"}'
    ts = _now_iso()
    sig_header = _sign_request(
        method="POST",
        target="/v1/echo",
        host="testserver",
        timestamp=ts,
        body=body,
        institution_id=DEMO_INSTITUTION,
        secret=DEMO_SECRET,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/echo",
            content=body,
            headers={
                "x-sbs-timestamp": ts,
                "x-sbs-signature": sig_header,
                "x-sbs-institution-id": DEMO_INSTITUTION,
            },
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["institution_id"] == DEMO_INSTITUTION


@pytest.mark.asyncio
async def test_missing_signature_header(
    hmac_settings, db_schema, fake_redis, test_database_url
):
    await _seed_secrets(test_database_url)
    await reset_engine_for_test()
    app = _make_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/echo",
            content=b"",
            headers={
                "x-sbs-timestamp": _now_iso(),
                "x-sbs-institution-id": DEMO_INSTITUTION,
            },
        )
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "SBS-401-010"
    assert body["type"].endswith("/SIGNATURE_MISSING_HEADER")


@pytest.mark.asyncio
async def test_unsupported_algorithm_prefix(
    hmac_settings, db_schema, fake_redis, test_database_url
):
    await _seed_secrets(test_database_url)
    await reset_engine_for_test()
    app = _make_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/echo",
            content=b"",
            headers={
                "x-sbs-timestamp": _now_iso(),
                "x-sbs-signature": "hmac-sha1-v0=" + base64.b64encode(b"x").decode(),
                "x-sbs-institution-id": DEMO_INSTITUTION,
            },
        )
    body = resp.json()
    assert body["code"] == "SBS-401-011"
    assert body["type"].endswith("/SIGNATURE_ALGORITHM_UNSUPPORTED")


@pytest.mark.asyncio
async def test_tampered_signature(
    hmac_settings, db_schema, fake_redis, test_database_url
):
    await _seed_secrets(test_database_url)
    await reset_engine_for_test()
    app = _make_app()
    ts = _now_iso()
    # Sign with the wrong key.
    sig_header = _sign_request(
        method="POST",
        target="/v1/echo",
        host="testserver",
        timestamp=ts,
        body=b"",
        institution_id=DEMO_INSTITUTION,
        secret=b"\x00" * 32,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/echo",
            content=b"",
            headers={
                "x-sbs-timestamp": ts,
                "x-sbs-signature": sig_header,
                "x-sbs-institution-id": DEMO_INSTITUTION,
            },
        )
    body = resp.json()
    assert body["code"] == "SBS-401-012"
    assert body["type"].endswith("/SIGNATURE_INVALID")


@pytest.mark.asyncio
async def test_expired_timestamp(
    hmac_settings, db_schema, fake_redis, test_database_url
):
    await _seed_secrets(test_database_url)
    await reset_engine_for_test()
    app = _make_app()
    old_ts = (
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    sig_header = _sign_request(
        method="POST",
        target="/v1/echo",
        host="testserver",
        timestamp=old_ts,
        body=b"",
        institution_id=DEMO_INSTITUTION,
        secret=DEMO_SECRET,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/echo",
            content=b"",
            headers={
                "x-sbs-timestamp": old_ts,
                "x-sbs-signature": sig_header,
                "x-sbs-institution-id": DEMO_INSTITUTION,
            },
        )
    body = resp.json()
    assert body["code"] == "SBS-401-013"
    assert body["type"].endswith("/SIGNATURE_EXPIRED")


@pytest.mark.asyncio
async def test_replay_detected(
    hmac_settings, db_schema, fake_redis, test_database_url
):
    await _seed_secrets(test_database_url)
    await reset_engine_for_test()
    app = _make_app()
    ts = _now_iso()
    sig_header = _sign_request(
        method="POST",
        target="/v1/echo",
        host="testserver",
        timestamp=ts,
        body=b"",
        institution_id=DEMO_INSTITUTION,
        secret=DEMO_SECRET,
    )
    headers = {
        "x-sbs-timestamp": ts,
        "x-sbs-signature": sig_header,
        "x-sbs-institution-id": DEMO_INSTITUTION,
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        first = await ac.post("/v1/echo", content=b"", headers=headers)
        second = await ac.post("/v1/echo", content=b"", headers=headers)

    assert first.status_code == 200, first.text
    body = second.json()
    assert second.status_code == 401
    assert body["code"] == "SBS-401-014"
    assert body["type"].endswith("/SIGNATURE_REPLAYED")


@pytest.mark.asyncio
async def test_institution_mismatch_with_mtls_subject(
    hmac_settings, db_schema, fake_redis, test_database_url
):
    await _seed_secrets(test_database_url)
    await reset_engine_for_test()
    app = _make_app()
    ts = _now_iso()
    # Sign with a different institution_id than the mTLS bypass sentinel
    # (which is SBS-001234).
    sig_header = _sign_request(
        method="POST",
        target="/v1/echo",
        host="testserver",
        timestamp=ts,
        body=b"",
        institution_id="SBS-005678",
        secret=DEMO_SECRET,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/echo",
            content=b"",
            headers={
                "x-sbs-timestamp": ts,
                "x-sbs-signature": sig_header,
                "x-sbs-institution-id": "SBS-005678",
            },
        )
    body = resp.json()
    assert resp.status_code == 401
    assert body["code"] == "SBS-401-015"
    assert body["type"].endswith("/SIGNATURE_INSTITUTION_MISMATCH")
