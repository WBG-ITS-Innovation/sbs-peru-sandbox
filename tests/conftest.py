"""Pytest configuration for the workflow-harness and runtime tests.

The repo is a uv workspace; dev dependencies (pytest, openai, python-dotenv,
gitpython, pyyaml) live in the root pyproject.toml's `dev` group. Run from
repo root:

    uv sync --all-groups
    uv run pytest tests/

The HTTP layer tests use ``httpx.AsyncClient`` with an ASGI transport so
the app is exercised in-process. Database-backed tests provision a
Postgres testcontainer per session, guarded by a database-name regex check
so a misconfigured ``TEST_DATABASE_URL`` cannot point the tests at the dev
database.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import re
import sys
from typing import AsyncIterator

import pytest
import pytest_asyncio

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Make scripts/ importable so the tests can pull functions out of close_prompt.py
# without running the script's argparse / sys.exit path.
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# Make api/ importable so tests can `from sbs_api ... import ...`. The api/
# workspace member is `package = false` in pyproject.toml (it is consumed in
# place, not installed); see ADR 0023.
sys.path.insert(0, str(REPO_ROOT / "api"))


# --- DB-name guardrail --------------------------------------------------------

_TEST_DB_NAME_RE = re.compile(r"^test_[A-Za-z0-9_]+$")


def _verify_test_db_url(url: str) -> None:
    """Refuse to operate against any database whose name doesn't look like a test DB.

    Defends against the failure mode: `TEST_DATABASE_URL` was set to the dev
    DSN, the test fixture wipes everything. The pattern matches any DB whose
    name starts with ``test_``. The testcontainer path always names the DB
    ``test_sbs``; a manually-set fallback must do the same.
    """

    # Pull the path component after the last `/`. Strip query string.
    name = url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
    if not _TEST_DB_NAME_RE.match(name):
        raise RuntimeError(
            f"Refusing to run tests against database name {name!r}. "
            "The test fixture requires a database whose name matches "
            "^test_ (e.g. 'test_sbs')."
        )


# --- Fixtures gated on Docker availability -----------------------------------


def _docker_available() -> bool:
    if os.environ.get("TEST_DATABASE_URL"):
        return True
    try:
        import docker  # type: ignore[import-untyped]

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


pytestmark_db = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker unavailable and TEST_DATABASE_URL not set — DB-backed tests skipped",
)


@pytest_asyncio.fixture(scope="session")
async def test_database_url() -> AsyncIterator[str]:
    """Yield a Postgres URL suitable for the FastAPI app to talk to.

    Two paths:
    1. ``TEST_DATABASE_URL`` env var — used as-is after the DB-name guardrail.
    2. Default — start a pgvector testcontainer with DB name ``test_sbs``.
    """

    env_url = os.environ.get("TEST_DATABASE_URL")
    if env_url:
        _verify_test_db_url(env_url)
        yield env_url
        return

    # Lazy import: testcontainers pulls in docker-py which has surprising
    # import-time cost.
    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="sbs",
        password="sbs",  # pragma: allowlist secret
        dbname="test_sbs",
    ) # pragma: allowlist secret
    container.start()
    try:
        host_url = container.get_connection_url()
        # testcontainers returns postgresql+psycopg2 by default; rewrite to asyncpg.
        async_url = host_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        _verify_test_db_url(async_url)

        # Create the pgvector extension. The init script in docker-compose is
        # not run by testcontainers, so do it explicitly.
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(async_url)
        async with engine.begin() as conn:
            from sqlalchemy import text

            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await engine.dispose()
        yield async_url
    finally:
        container.stop()


@pytest_asyncio.fixture()
async def app_settings(test_database_url, monkeypatch):
    """Per-test :class:`Settings` with the testcontainer DSN and stub auth."""

    monkeypatch.setenv("SBS_API_DATABASE_URL", test_database_url)
    monkeypatch.setenv("SBS_API_AUTH_STUB_ENABLED", "true")
    monkeypatch.setenv("SBS_API_AUTH_STUB_INSTITUTION_ID", "SBS-001234")
    monkeypatch.setenv("SBS_API_LOG_FORMAT", "json")
    monkeypatch.setenv("SBS_API_OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "test")
    monkeypatch.setenv("SBS_API_MAX_REQUEST_BODY_BYTES", "262144")

    from sbs_api.config import get_settings

    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest_asyncio.fixture()
async def db_schema(test_database_url):
    """Provision the schema on the testcontainer once per test.

    Drops and re-creates so each test sees a clean DB. Seeds two demo
    institutions (BANCO_DEMO_001 → SBS-001234 and COOPAC_DEMO_002 → SBS-005678)
    plus three complaints.
    """

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    engine = create_async_engine(test_database_url)

    # Apply the migration via Base.metadata (lighter than alembic — full
    # migration tested in test_alembic_migration).
    from sbs_api.db.base import Base
    from sbs_api.db import models  # noqa: F401  - import for metadata side effects
    from sbs_api.db.models.complaint import ComplaintRecord
    from sbs_api.db.models.institution import InstitutionRecord

    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version CASCADE"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO alembic_version (version_num) VALUES ('20260518_0001')"
            )
        )

    # Seed.
    from sqlalchemy.ext.asyncio import async_sessionmaker

    SessionMaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    from datetime import date

    async with SessionMaker() as session:
        session.add_all(
            [
                InstitutionRecord(
                    institution_id="SBS-001234",
                    display_name="BANCO_DEMO_001",
                    onboarded=True,
                    rate_limit_per_minute=60,
                    schema_version="v0.1.0",
                ),
                InstitutionRecord(
                    institution_id="SBS-005678",
                    display_name="COOPAC_DEMO_002",
                    onboarded=True,
                    rate_limit_per_minute=60,
                    schema_version="v0.1.0",
                ),
            ]
        )
        session.add_all(
            [
                ComplaintRecord(
                    complaint_id=f"BCO-2026-{i:06d}",
                    institution_id="SBS-001234",
                    received_date=date(2026, 5, 10 + i),
                    complainant_doc_type="DNI",
                    product_category="TARJETA_CREDITO",
                    channel="APP_MOVIL",
                    motivo_code="COBRO_INDEBIDO",
                    severity="HIGH",
                    description_text="Cargo no autorizado por S/ 245.00 — pendiente.",
                    description_language="es",
                    complainant_age_range="35_44",
                    complainant_district="150100",
                    submission_method="APP_MOVIL",
                    original_reference_id=None,
                    resolution_status="pendiente",
                )
                for i in range(1, 4)
            ]
        )
        await session.commit()

    yield

    await engine.dispose()


@pytest_asyncio.fixture()
async def app(app_settings, db_schema):
    """Build a fresh FastAPI app per test."""

    from sbs_api.db.session import reset_engine_for_test
    from sbs_api.app import create_app

    await reset_engine_for_test()
    application = create_app(settings=app_settings)
    yield application
    await reset_engine_for_test()


@pytest_asyncio.fixture()
async def client(app):
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
