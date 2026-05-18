"""Health probe semantics — live, ready, startup.

ADR 0030 — three probes with explicit semantics. ``/live`` always 200,
``/ready`` performs a DB ping with a 1-second cache, ``/startup`` checks
the alembic_version table.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


async def test_live_always_200(client):
    """No DB / IO required — always 200."""

    r = await client.get("/v1/health/live")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


async def test_ready_200_with_healthy_db(client):
    # Reset the ready-cache so we exercise a fresh DB ping.
    from sbs_api.routes.meta import _reset_ready_cache_for_test

    _reset_ready_cache_for_test()
    r = await client.get("/v1/health/ready")
    assert r.status_code == 200


async def test_ready_cache_window_returns_same_result(client):
    """Two calls within the cache window do not hit the DB twice.

    Observable form: clear the cache, call /ready, then break the engine,
    then call /ready again — the second call should still 200 because the
    cached "ok" survives.
    """

    from sbs_api.routes.meta import _reset_ready_cache_for_test
    from sbs_api.db import session as db_session

    _reset_ready_cache_for_test()
    r1 = await client.get("/v1/health/ready")
    assert r1.status_code == 200

    # Re-point at a port nothing listens on so a fresh ping would fail. The
    # cache should still hold for `readiness_cache_seconds` (1.0s by default).
    real_engine = db_session._engine
    db_session._engine = None
    db_session._sessionmaker = None
    from sqlalchemy.ext.asyncio import create_async_engine

    db_session._engine = create_async_engine(
        "postgresql+asyncpg://invalid:invalid@127.0.0.1:1/test_nope"  # pragma: allowlist secret
    )
    try:
        r2 = await client.get("/v1/health/ready")
        # The cache is global to the process, so the second call should
        # still return 200 from the cache.
        assert r2.status_code == 200
    finally:
        # Restore.
        await db_session._engine.dispose()
        db_session._engine = real_engine
        db_session._sessionmaker = None


async def test_startup_200_when_alembic_version_present(client):
    """The fixture inserts ('20260518_0001') into alembic_version on setup."""

    r = await client.get("/v1/health/startup")
    assert r.status_code == 200


async def test_traceparent_header_on_health_responses(client):
    # With OTel's no-op exporter no real span exists, so the response header
    # may be absent — but it MUST not be malformed when present.
    r = await client.get("/v1/health/live")
    tp = r.headers.get("traceparent")
    if tp is not None:
        # 00-<32hex>-<16hex>-<2hex>
        parts = tp.split("-")
        assert len(parts) == 4
        assert len(parts[1]) == 32
        assert len(parts[2]) == 16
