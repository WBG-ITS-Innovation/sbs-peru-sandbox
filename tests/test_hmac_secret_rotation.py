"""Secret rotation grace window — workstream B.

ADR 0027 amendment: an institution may rotate its HMAC secret by moving
``active_secret`` → ``previous_secret`` and storing a new value in
``active_secret``. Requests signed with the previous secret continue to
verify until ``previous_secret_retires_at`` passes (default 1 hour after
rotation).

Tests exercise three states:
  1. Signed with previous_secret during the grace window → accepted.
  2. Signed with previous_secret after grace expiry → rejected.
  3. previous_secret is NULL → only active_secret accepted.
"""

from __future__ import annotations

import datetime as dt

import fakeredis.aioredis
import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from sbs_api.auth.hmac import build_canonical_request, compute_signature
from sbs_api.config import get_settings
from sbs_api.db.session import reset_engine_for_test
from sbs_api.dependencies.hmac_verify import (
    override_redis_for_test,
    reset_redis_for_test,
    verified_hmac_signature,
)
from sbs_api.dependencies.mtls import MtlsSubject

DEMO_INSTITUTION = "SBS-001234"
ACTIVE_SECRET = b"\xaa" * 32
PREVIOUS_SECRET = b"\xbb" * 32


@pytest_asyncio.fixture()
async def rotation_settings(test_database_url, monkeypatch):
    monkeypatch.setenv("SBS_API_DATABASE_URL", test_database_url)
    monkeypatch.setenv("SBS_API_MTLS_MODE", "disabled")
    monkeypatch.setenv("SBS_API_DISABLE_MTLS_FOR_TESTS", "true")
    monkeypatch.setenv("SBS_API_AUTH_STUB_ENABLED", "false")
    monkeypatch.setenv("SBS_API_LOG_FORMAT", "json")
    monkeypatch.setenv("SBS_API_OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "test")
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


async def _seed_with_previous(
    test_database_url: str,
    *,
    previous_retires_at: dt.datetime | None,
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
                "iid": DEMO_INSTITUTION,
                "act": ACTIVE_SECRET,
                "prev": PREVIOUS_SECRET,
                "prev_ret": previous_retires_at,
            },
        )
    await engine.dispose()


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.post("/v1/echo")
    async def echo(subject: MtlsSubject = Depends(verified_hmac_signature)) -> dict:
        return {"institution_id": subject.institution_id}

    from sbs_api.errors.handlers import install_exception_handlers

    install_exception_handlers(app)
    return app


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sign(secret: bytes) -> tuple[str, str]:
    ts = _now_iso()
    canonical = build_canonical_request(
        method="POST",
        target="/v1/echo",
        host="testserver",
        timestamp=ts,
        body=b"",
        institution_id=DEMO_INSTITUTION,
    )
    sig = compute_signature(secret, canonical)
    return ts, f"hmac-sha256-v1={sig}"


@pytest.mark.asyncio
async def test_previous_secret_accepted_during_grace(
    rotation_settings, db_schema, fake_redis, test_database_url
):
    grace_end = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    await _seed_with_previous(test_database_url, previous_retires_at=grace_end)
    await reset_engine_for_test()

    ts, sig_header = _sign(PREVIOUS_SECRET)
    app = _make_app()
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
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_previous_secret_rejected_after_grace(
    rotation_settings, db_schema, fake_redis, test_database_url
):
    expired = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
    await _seed_with_previous(test_database_url, previous_retires_at=expired)
    await reset_engine_for_test()

    ts, sig_header = _sign(PREVIOUS_SECRET)
    app = _make_app()
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
    assert resp.status_code == 401
    assert body["code"] == "SBS-401-012"
    assert body["type"].endswith("/SIGNATURE_INVALID")


@pytest.mark.asyncio
async def test_previous_secret_null_only_active_accepted(
    rotation_settings, db_schema, fake_redis, test_database_url
):
    # Seed with previous=NULL.
    engine = create_async_engine(test_database_url)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO institution_secrets "
                "(institution_id, active_secret, rotated_at, created_at) "
                "VALUES (:iid, :act, now(), now()) "
                "ON CONFLICT (institution_id) DO UPDATE SET "
                "active_secret = excluded.active_secret, "
                "previous_secret = NULL, "
                "previous_secret_retires_at = NULL"
            ),
            {"iid": DEMO_INSTITUTION, "act": ACTIVE_SECRET},
        )
    await engine.dispose()
    await reset_engine_for_test()

    # Active passes.
    ts, sig_active = _sign(ACTIVE_SECRET)
    # Previous (which the institution thinks is active) fails.
    _ts2, sig_prev = _sign(PREVIOUS_SECRET)

    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        good = await ac.post(
            "/v1/echo",
            content=b"",
            headers={
                "x-sbs-timestamp": ts,
                "x-sbs-signature": sig_active,
                "x-sbs-institution-id": DEMO_INSTITUTION,
            },
        )
        bad = await ac.post(
            "/v1/echo",
            content=b"",
            headers={
                "x-sbs-timestamp": _ts2,
                "x-sbs-signature": sig_prev,
                "x-sbs-institution-id": DEMO_INSTITUTION,
            },
        )

    assert good.status_code == 200, good.text
    assert bad.status_code == 401
    assert bad.json()["code"] == "SBS-401-012"
