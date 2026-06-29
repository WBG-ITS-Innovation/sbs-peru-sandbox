# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for the P-RESHAPE-8.5 cockpit tests.

A shared-secret app fixture (``secret_app``), a dev-stub app fixture
(``stub_app``) for the stub-auth check, persona header helpers, and an
``agent_runs`` seeder so the unified monitoring tests have data.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

SHARED = "sandbox-cockpit-85-test-001"  # pragma: allowlist secret


@pytest.fixture
async def secret_app(app_settings, monkeypatch, db_schema):
    monkeypatch.setenv("SBS_API_INTERNAL_API_SECRET", SHARED)
    from sbs_api.config import get_settings

    get_settings.cache_clear()
    from sbs_api.app import create_app
    from sbs_api.db.session import reset_engine_for_test

    await reset_engine_for_test()
    application = create_app(settings=get_settings())
    try:
        yield application
    finally:
        await reset_engine_for_test()
        get_settings.cache_clear()


@pytest.fixture
async def stub_app(app_settings, monkeypatch, db_schema):
    """Dev + auth_stub_enabled so ``Bearer stub:<persona>`` is honoured."""
    monkeypatch.setenv("SBS_API_AUTH_STUB_ENABLED", "true")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "dev")
    monkeypatch.setenv("SBS_API_INTERNAL_API_SECRET", SHARED)
    from sbs_api.config import get_settings

    get_settings.cache_clear()
    from sbs_api.app import create_app
    from sbs_api.db.session import reset_engine_for_test

    await reset_engine_for_test()
    application = create_app(settings=get_settings())
    try:
        yield application
    finally:
        await reset_engine_for_test()
        get_settings.cache_clear()


def hdr(role: str, **extra) -> dict[str, str]:
    h = {"Authorization": f"Bearer {SHARED}", "X-SBS-Role": role}
    h.update(extra)
    return h


async def seed_agent_runs(test_database_url: str, runs: list[dict]) -> list[str]:
    """Insert agent_runs rows. Each spec: agent_name, status, and optional
    started_minutes_ago / duration_ms / final_output / complaint_id / id."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sbs_api.db.models.agent_run import AgentRun

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(tz=timezone.utc)
    ids: list[str] = []
    async with SM() as session:
        for r in runs:
            rid = r.get("id") or str(uuid.uuid4())
            status = r["status"]
            started = now - timedelta(minutes=r.get("started_minutes_ago", 60))
            ended = (
                None
                if status == "in_progress"
                else started + timedelta(milliseconds=r.get("duration_ms", 200))
            )
            session.add(
                AgentRun(
                    id=rid,
                    complaint_id=r.get("complaint_id", "BCO-2026-000001"),
                    agent_name=r["agent_name"],
                    agent_version=f"{r['agent_name']}-0.1.0",
                    started_at=started,
                    ended_at=ended,
                    status=status,
                    tool_calls=[],
                    final_output=r.get("final_output"),
                    error=None,
                )
            )
            ids.append(rid)
        await session.commit()
    await engine.dispose()
    return ids
