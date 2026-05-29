"""The baseline migration applies cleanly to a fresh Postgres testcontainer.

ADR 0030's startup probe asserts that ``alembic_version`` is *present* (not
that it matches a specific revision — that's the operational policy, see
ADR 0030 §Consequences). This test exercises a stronger property: the
baseline migration applies cleanly against a fresh DB and records the
exact head revision. Together with the probe's looser presence-only check,
deployments cannot serve traffic against an unmigrated database, and the
migration is exercised end-to-end on every test run.
"""

from __future__ import annotations

import asyncio
import pathlib

import pytest

from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


async def _drop_schema(test_database_url: str) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(test_database_url)
    async with engine.begin() as conn:
        # Drop in reverse-dependency order so FKs are released before
        # their parents. CASCADE handles indirect dependents.
        for table in (
            "alembic_version",
            "agent_feedback",
            "supervisory_observations",
            "pending_approvals",
            "complaint_narrative_drafts",
            "audit_events",
            "agent_runs",
            "raw_complaints",
            "webhook_deliveries",
            "outbound_webhook_secrets",
            "institution_webhook_configs",
            "batch_row_rejections",
            "oauth_clients",
            "institution_secrets",
            "institution_certificates",
            "idempotency_records",
            "batches",
            "complaints",
            "institutions",
        ):
            await conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
    await engine.dispose()


async def _inspect_tables(test_database_url: str) -> tuple[set[str], str | None]:
    from sqlalchemy import inspect, text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(test_database_url)
    async with engine.connect() as conn:
        tables = set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
        version_num: str | None = None
        if "alembic_version" in tables:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            version_num = result.scalar()
    await engine.dispose()
    return tables, version_num


def _run_alembic_in_thread(test_database_url: str) -> None:
    """Alembic's env.py calls ``asyncio.run`` — wrap in a thread so the
    test's outer event loop is not violated.
    """

    import threading

    def _go() -> None:
        from alembic import command
        from alembic.config import Config

        repo_root = pathlib.Path(__file__).resolve().parent.parent
        cfg = Config(str(repo_root / "api" / "alembic.ini"))
        cfg.set_main_option("script_location", str(repo_root / "api" / "migrations"))
        cfg.set_main_option("sqlalchemy.url", test_database_url)
        command.upgrade(cfg, "head")

    err: list[BaseException] = []

    def _wrap() -> None:
        try:
            _go()
        except BaseException as exc:  # noqa: BLE001
            err.append(exc)

    t = threading.Thread(target=_wrap)
    t.start()
    t.join()
    if err:
        raise err[0]


@pytest.mark.asyncio
async def test_baseline_migration_applies_cleanly(test_database_url, monkeypatch):
    """``alembic upgrade head`` on a fresh DB exits 0 and creates the tables."""

    monkeypatch.setenv("SBS_API_DATABASE_URL", test_database_url)
    from sbs_api.config import get_settings

    get_settings.cache_clear()

    await _drop_schema(test_database_url)
    # Alembic's env.py calls asyncio.run() — running it in a thread isolates
    # it from the test's outer event loop.
    await asyncio.to_thread(_run_alembic_in_thread, test_database_url)
    tables, version_num = await _inspect_tables(test_database_url)

    expected = {
        "institutions",
        "complaints",
        "batches",
        "batch_row_rejections",
        "idempotency_records",
        "institution_certificates",
        "institution_secrets",
        "institution_webhook_configs",
        "oauth_clients",
        "outbound_webhook_secrets",
        "webhook_deliveries",
        "agent_runs",
        "audit_events",
        "complaint_narrative_drafts",
        "pending_approvals",
        "supervisory_observations",
        "agent_feedback",
        "raw_complaints",
        "alembic_version",
    }
    missing = expected - tables
    assert not missing, f"missing tables: {missing}"
    # Part 12 added an additive migration that bumps the head past the
    # P11 demo-ui-polish overlay. The exact head string is recorded in
    # api/migrations/versions/ alongside the down-revision chain.
    assert version_num == "20260527_0001_agents_status"
