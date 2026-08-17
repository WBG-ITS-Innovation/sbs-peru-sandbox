# SPDX-License-Identifier: Apache-2.0
"""verified_oauth_token_with_scope dependency tests — workstream C.

A route declaring ``Depends(verified_oauth_token_with_scope("complaints:write"))``
must accept tokens carrying that scope and reject tokens missing it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from sbs_api.auth.oauth import IssueOptions, issue_token
from sbs_api.auth.scopes import (
    BATCH_UPLOAD,
    COMPLAINTS_READ,
    COMPLAINTS_WRITE,
)
from sbs_api.config import get_settings
from sbs_api.db.session import reset_engine_for_test
from sbs_api.dependencies.oauth import (
    override_signing_key_for_test,
    reset_signing_key_for_test,
    verified_oauth_token_with_scope,
)

BANCO_ID = "SBS-001234"
TEST_KEY = b"\x42" * 32
BYPASS_THUMBPRINT = "0" * 64


@pytest_asyncio.fixture()
async def scope_settings(test_database_url, monkeypatch):
    monkeypatch.setenv("SBS_API_DATABASE_URL", test_database_url)
    monkeypatch.setenv("SBS_API_MTLS_MODE", "disabled")
    monkeypatch.setenv("SBS_API_DISABLE_MTLS_FOR_TESTS", "true")
    monkeypatch.setenv("SBS_API_AUTH_STUB_ENABLED", "false")
    monkeypatch.setenv("SBS_API_LOG_FORMAT", "json")
    monkeypatch.setenv("SBS_API_OTEL_TRACES_EXPORTER", "none")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "test")
    get_settings.cache_clear()
    override_signing_key_for_test(TEST_KEY)
    yield get_settings()
    reset_signing_key_for_test()
    get_settings.cache_clear()


def _mint(scopes: set[str], *, exp_delta: timedelta = timedelta(minutes=15)) -> str:
    return issue_token(
        IssueOptions(
            institution_id=BANCO_ID,
            granted_scopes=frozenset(scopes),
            cert_thumbprint_sha256_hex=BYPASS_THUMBPRINT,
            ttl_seconds=int(exp_delta.total_seconds()),
        ),
        key=TEST_KEY,
    )


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.post("/v1/complaints")
    async def write_complaint(
        token=Depends(verified_oauth_token_with_scope(COMPLAINTS_WRITE)),
    ) -> dict:
        return {"institution_id": token.institution_id}

    @app.get("/v1/complaints")
    async def list_complaints(
        token=Depends(verified_oauth_token_with_scope(COMPLAINTS_READ)),
    ) -> dict:
        return {"institution_id": token.institution_id}

    from sbs_api.errors.handlers import install_exception_handlers

    install_exception_handlers(app)
    return app


@pytest.mark.asyncio
async def test_token_with_required_scope_accepted(scope_settings, db_schema):
    await reset_engine_for_test()
    app = _make_app()
    token = _mint({COMPLAINTS_WRITE, BATCH_UPLOAD})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/complaints",
            headers={"authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["institution_id"] == BANCO_ID


@pytest.mark.asyncio
async def test_token_missing_required_scope_rejected(scope_settings, db_schema):
    await reset_engine_for_test()
    app = _make_app()
    # Token has read but not write.
    token = _mint({COMPLAINTS_READ})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/complaints",
            headers={"authorization": f"Bearer {token}"},
        )
    body = resp.json()
    assert resp.status_code == 403
    assert body["code"] == "SBS-403-010"
    assert body["type"].endswith("/TOKEN_SCOPE_INSUFFICIENT")


@pytest.mark.asyncio
async def test_no_authorization_header_rejected(scope_settings, db_schema):
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post("/v1/complaints")
    body = resp.json()
    assert resp.status_code == 401
    assert body["code"] == "SBS-401-020"
    assert body["type"].endswith("/TOKEN_REQUIRED")


@pytest.mark.asyncio
async def test_non_bearer_scheme_rejected(scope_settings, db_schema):
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/complaints",
            headers={"authorization": "Basic AAAA"},
        )
    body = resp.json()
    assert resp.status_code == 401
    assert body["code"] == "SBS-401-020"


@pytest.mark.asyncio
async def test_expired_token_rejected(scope_settings, db_schema):
    await reset_engine_for_test()
    app = _make_app()
    expired = _mint({COMPLAINTS_WRITE}, exp_delta=timedelta(seconds=-30))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/complaints",
            headers={"authorization": f"Bearer {expired}"},
        )
    body = resp.json()
    assert resp.status_code == 401
    assert body["code"] == "SBS-401-022"
    assert body["type"].endswith("/TOKEN_EXPIRED")


@pytest.mark.asyncio
async def test_malformed_token_rejected(scope_settings, db_schema):
    await reset_engine_for_test()
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/complaints",
            headers={"authorization": "Bearer not.a.valid.token"},
        )
    body = resp.json()
    assert resp.status_code == 401
    assert body["code"] == "SBS-401-021"
    assert body["type"].endswith("/TOKEN_INVALID")
