# SPDX-License-Identifier: Apache-2.0
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
        # Schema-wide reset. Tests that apply real alembic migrations
        # (test_alembic_migration) create tables that have no model in
        # Base.metadata; metadata.drop_all cannot remove those, and their
        # FKs block dropping the tables it CAN see — erroring every
        # later db_schema setup. Nuking the schema is order-proof.
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO alembic_version (version_num) VALUES ('20260524_0001')"
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
                    tier_classification="large",
                    rate_limit_per_minute=None,
                    schema_version="v0.1.0",
                ),
                InstitutionRecord(
                    institution_id="SBS-005678",
                    display_name="COOPAC_DEMO_002",
                    onboarded=True,
                    tier_classification="small",
                    rate_limit_per_minute=None,
                    schema_version="v0.1.0",
                ),
            ]
        )
        # Flush institutions before complaints so the FK constraint sees them.
        await session.flush()

        # Outbound webhook wiring for BANCO_DEMO_001 — the DIValeVale
        # validation-delivery path (ADR 0035) refuses to deliver without
        # a config + secret row. Secret mirrors the tests' b"0" * 32.
        from sbs_api.db.models.institution_webhook_config import InstitutionWebhookConfig
        from sbs_api.db.models.outbound_webhook_secret import OutboundWebhookSecret
        session.add_all(
            [
                InstitutionWebhookConfig(
                    institution_id="SBS-001234",
                    callback_url="https://fi.sandbox.example.com/sbs-callback",
                    enabled=True,
                ),
                OutboundWebhookSecret(
                    institution_id="SBS-001234",
                    kid="sandbox-v1",
                    active_secret=b"0" * 32,
                ),
            ]
        )

        # Brand aliases + the 14-signal social fixture campaign
        # (P-RESHAPE-6) that tests/ingestion/social expects seeded.
        from datetime import datetime, timezone
        from decimal import Decimal
        from sbs_api.db.models.fi_brand_alias import FIBrandAlias
        from sbs_api.db.models.social_signal import SocialSignalFixture
        from sbs_api.ingestion.social.entity_resolver import normalize_alias
        session.add_all(
            [
                FIBrandAlias(
                    institution_id="SBS-001234",
                    alias_normalized=normalize_alias(raw),
                    alias_kind=kind,
                )
                for raw, kind in [
                    ("banco demo", "display"),
                    ("bancodemo", "handle"),
                    ("bcodemo.pe", "domain"),
                ]
            ]
        )
        _fx = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
        session.add_all(
            [
                SocialSignalFixture(
                    signal_id=f"FIX-2026-{i:04d}",
                    source="FIXTURE",
                    source_post_id=f"fixture-post-{i:04d}",
                    captured_at=_fx,
                    post_authored_at=_fx,
                    post_text_es=(
                        "Cuidado con el phishing de banco demo — enlace "
                        f"sospechoso reportado, caso {i}. [HANDLE] eliminado."
                    ),
                    detected_institution_codes=["SBS-001234"],
                    detected_fraud_indicators=["PHISHING_KEYWORD"],
                    engagement_score=Decimal("10.500"),
                    raw_url=f"https://social.sandbox.example.com/post/{i}",
                )
                for i in range(1, 15)
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
                    source="api_realtime",
                )
                for i in range(1, 4)
            ]
            # Tier 2 batch-ingested complaints for COOPAC_DEMO_002. Mirrors
            # the dev-seed.sql block so the cockpit Tier 2 panel has rows
            # to render in tests and in the local dev DB. source='batch'
            # matches the worker contract (ADR 0034).
            + [
                ComplaintRecord(
                    complaint_id=f"COP-2026-{i:06d}",
                    institution_id="SBS-005678",
                    received_date=date(2026, 5, 9 + i * 2),
                    complainant_doc_type="DNI",
                    product_category="COOPAC",
                    channel="AGENCIA",
                    motivo_code="DEMORA_ATENCION",
                    severity="MEDIUM",
                    description_text=(
                        "Aporte mensual no acreditado en mi cuenta cooperativa. "
                        "Solicito la acreditación correspondiente."
                    ),
                    description_language="es",
                    complainant_age_range="35_44",
                    complainant_district="150100",
                    submission_method="AGENCIA",
                    original_reference_id=None,
                    resolution_status="pendiente",
                    source="batch",
                )
                for i in range(1, 4)
            ]
        )
        await session.commit()

    yield

    await engine.dispose()


@pytest_asyncio.fixture()
async def app(app_settings, db_schema):
    """Build a fresh FastAPI app per test.

    After workstream F.7 the protected routes use the real auth chain
    (mTLS → OAuth scope → business rate limit). To keep the existing
    endpoint tests simple, this fixture installs dependency overrides
    that bypass the chain:

    * ``verified_mtls_subject`` returns a fixed BANCO_DEMO_001 MtlsSubject
      (mirrors the auth-stub default institution_id=SBS-001234).
    * ``verified_oauth_token_with_scope(*scopes)`` for every scope set
      the protected routes declare returns a VerifiedToken with all
      four scopes granted.
    * ``business_bucket`` and ``oauth_token_bucket`` skip the rate
      limiter, returning the same MtlsSubject.
    * A fakeredis client is installed for any path that still touches
      Redis (HMAC replay cache, rate limit bucket implementation).

    Tests that want to exercise the real auth chain end-to-end should
    use the dedicated fixtures in test_rate_limiter*.py and the
    workstream B/C test files. Tests that want a 401 from the chain
    can pop the override they care about via
    ``app.dependency_overrides.pop(verified_mtls_subject, None)``.
    """

    import fakeredis.aioredis

    from sbs_api.app import create_app
    from sbs_api.auth.scopes import ALL_SCOPES
    from sbs_api.db.session import reset_engine_for_test
    from sbs_api.dependencies.hmac_verify import (
        override_redis_for_test,
        reset_redis_for_test,
        verified_hmac_signature,
    )
    from sbs_api.dependencies.mtls import MtlsSubject, verified_mtls_subject
    from sbs_api.dependencies.oauth import (
        VerifiedToken,
        verified_oauth_token_with_scope,
    )
    from sbs_api.dependencies.rate_limit import (
        business_bucket,
        oauth_token_bucket,
    )

    await reset_engine_for_test()
    application = create_app(settings=app_settings)

    # mTLS bypass — fixed BANCO_DEMO_001 subject.
    bypass_subject = MtlsSubject(
        institution_id="SBS-001234",
        cn="BANCO_DEMO_001",
        cert_thumbprint="0" * 64,
    )

    async def _mtls_bypass() -> MtlsSubject:
        return bypass_subject

    application.dependency_overrides[verified_mtls_subject] = _mtls_bypass

    # OAuth scope-set bypass — install overrides for every scope set
    # the protected routes declare. The factory's closure cache means
    # each ``verified_oauth_token_with_scope(SCOPE)`` returns a stable
    # function reference, which is what ``dependency_overrides`` keys
    # on.
    granted_all = frozenset(ALL_SCOPES)
    test_token = VerifiedToken(
        institution_id="SBS-001234",
        granted_scopes=granted_all,
        cert_thumbprint="0" * 64,
    )

    async def _oauth_bypass() -> VerifiedToken:
        return test_token

    for scope in ALL_SCOPES:
        dep = verified_oauth_token_with_scope(scope)
        application.dependency_overrides[dep] = _oauth_bypass

    # Rate-limit bypass — return the mTLS subject without consuming
    # any bucket capacity. Tests that exercise the limiter wire it up
    # explicitly.
    async def _bucket_bypass() -> MtlsSubject:
        return bypass_subject

    application.dependency_overrides[business_bucket] = _bucket_bypass
    application.dependency_overrides[oauth_token_bucket] = _bucket_bypass

    # HMAC bypass — returns the same mTLS subject without verifying any
    # signature. Tests that want to exercise the HMAC dep proper use
    # the dedicated fixtures in tests/test_hmac_*.py and the auth-chain
    # smoke test in scripts/smoke-test-auth.sh.
    application.dependency_overrides[verified_hmac_signature] = _bucket_bypass

    # Fakeredis for any code path that still touches the real client
    # (HMAC replay cache lookups from a workstream-B-enabled route).
    fake = fakeredis.aioredis.FakeRedis(decode_responses=False)
    override_redis_for_test(fake)

    try:
        yield application
    finally:
        await fake.aclose()
        reset_redis_for_test()
        await reset_engine_for_test()


@pytest_asyncio.fixture()
async def client(app):
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
