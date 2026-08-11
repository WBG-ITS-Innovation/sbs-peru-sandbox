# SPDX-License-Identifier: Apache-2.0
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
    """Reset the test database schema-wide (list-free).

    The previous implementation dropped a hardcoded table list that predated
    the P-RESHAPE migrations; tables not on the list survived and made the
    subsequent ``alembic upgrade head`` collide (DuplicateTableError).
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(test_database_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        # The schema drop also removed the pgvector extension conftest
        # installed at session start; restore it for every later test.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
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
    # 20260810_0001 adds the nullable agent_runs.model_provider column.
    assert version_num == "20260810_0001"


# --- autogenerate parity ---------------------------------------------------
#
# tests/test_orm_model_registry.py guards one direction: every model on disk
# must reach Base.metadata. It cannot guard the other, because a table that
# exists only in a migration has no model file to walk — which is exactly how
# sector_broadcasts, sector_broadcast_deliveries, sector_broadcast_audit and
# persona_tasks came to have no model at all. Alembic read all four as tables
# to DROP, so `alembic revision --autogenerate` was a live footgun.
#
# This test closes that direction: migrate a scratch DB to head, diff it
# against Base.metadata the way autogenerate does, and fail on any
# table-level operation.


def _table_level_diffs(diffs: list) -> list:
    """Keep only add/remove-table entries from a compare_metadata diff.

    compare_metadata yields a flat list whose entries are either a tuple
    ``(op_name, obj, ...)`` or a list of such tuples (grouped per table).
    """
    flat: list = []
    for entry in diffs:
        flat.extend(entry if isinstance(entry, list) else [entry])
    return [d for d in flat if d and d[0] in ("add_table", "remove_table")]


def _describe(diffs: list) -> list[str]:
    flat: list = []
    for entry in diffs:
        flat.extend(entry if isinstance(entry, list) else [entry])
    out: list[str] = []
    for d in flat:
        if not d:
            continue
        name = getattr(d[1], "name", None) if len(d) > 1 else None
        out.append(f"{d[0]}:{name}" if name else str(d[0]))
    return out


@pytest.mark.asyncio
async def test_autogenerate_finds_no_table_level_drift(
    test_database_url, monkeypatch
):
    """A migrated DB and Base.metadata agree on which tables exist.

    Failure means one of two things:

    * a table is created by a migration but has no ORM model — autogenerate
      would emit ``op.drop_table`` for it, and a maintainer who trusts the
      generated file drops live data; or
    * a model was added without a migration — autogenerate would emit
      ``op.create_table`` and the model is not deployed anywhere.

    Both are fixed by making the two sides agree, never by editing this
    test.

    Index-level differences are deliberately NOT asserted here. Four
    indexes (ix_complaints_flag_unknown_taxonomy,
    ix_institution_certificates_cn,
    ix_institution_certificates_institution_id,
    ix_oauth_clients_institution_id) are created by migrations without a
    matching Index() in their model, so autogenerate reports them as
    removed and recreates them under op.f() names in downgrade(). That is
    cosmetic naming churn, it is tracked separately, and folding it in here
    would mean either renaming indexes across shipped migrations or leaving
    a permanently red test — neither of which protects anyone from the
    data-loss case this test exists to catch.
    """

    monkeypatch.setenv("SBS_API_DATABASE_URL", test_database_url)
    from sbs_api.config import get_settings

    get_settings.cache_clear()

    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy.ext.asyncio import create_async_engine

    from sbs_api.db import models  # noqa: F401 — import for metadata side effects
    from sbs_api.db.base import Base

    await _drop_schema(test_database_url)
    await asyncio.to_thread(_run_alembic_in_thread, test_database_url)

    def _compare(sync_conn) -> list:
        # compare_type mirrors api/migrations/env.py so this diff is the
        # same one a maintainer would get from the alembic CLI.
        ctx = MigrationContext.configure(
            sync_conn, opts={"compare_type": True}
        )
        return compare_metadata(ctx, Base.metadata)

    engine = create_async_engine(test_database_url)
    try:
        async with engine.connect() as conn:
            diffs = await conn.run_sync(_compare)
    finally:
        await engine.dispose()

    table_diffs = _table_level_diffs(diffs)
    assert not table_diffs, (
        "alembic autogenerate reports table-level drift between the "
        "migrated schema and Base.metadata:\n  "
        + "\n  ".join(
            f"{op}: {getattr(obj, 'name', obj)}" for op, obj, *_ in table_diffs
        )
        + "\n\nremove_table means a migration-created table has no ORM model "
        "(autogenerate would DROP it); add_table means a model has no "
        "migration. Fix the code, not this test.\n"
        f"full diff for context: {_describe(diffs)}"
    )
