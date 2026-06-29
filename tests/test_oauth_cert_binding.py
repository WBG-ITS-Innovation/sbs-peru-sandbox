# SPDX-License-Identifier: Apache-2.0
"""RFC 8705 cert-binding tests — workstream C.

A token issued for cert thumbprint X must be rejected when presented
over a connection where the mTLS subject has thumbprint Y. The mTLS
dependency is left at the bypass sentinel (thumbprint = '0' * 64) so
the only variable is what the token's cnf.x5t#S256 claim carries.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from sbs_api.auth.oauth import IssueOptions, issue_token
from sbs_api.auth.scopes import COMPLAINTS_WRITE
from sbs_api.config import get_settings
from sbs_api.db.session import reset_engine_for_test
from sbs_api.dependencies.oauth import (
    override_signing_key_for_test,
    reset_signing_key_for_test,
    verified_oauth_token_with_scope,
)

BANCO_ID = "SBS-001234"
TEST_KEY = b"\xfe" * 32
BYPASS_THUMBPRINT = "0" * 64
WRONG_THUMBPRINT = "f" * 64


@pytest_asyncio.fixture()
async def binding_settings(test_database_url, monkeypatch):
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


def _mint_for_thumbprint(thumbprint: str, *, sub: str = BANCO_ID) -> str:
    return issue_token(
        IssueOptions(
            institution_id=sub,
            granted_scopes=frozenset({COMPLAINTS_WRITE}),
            cert_thumbprint_sha256_hex=thumbprint,
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

    from sbs_api.errors.handlers import install_exception_handlers

    install_exception_handlers(app)
    return app


@pytest.mark.asyncio
async def test_token_thumbprint_matches_mtls_subject(binding_settings, db_schema):
    await reset_engine_for_test()
    app = _make_app()
    # Mint a token bound to the bypass sentinel thumbprint.
    token = _mint_for_thumbprint(BYPASS_THUMBPRINT)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/complaints",
            headers={"authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_token_thumbprint_mismatch_rejected(binding_settings, db_schema):
    await reset_engine_for_test()
    app = _make_app()
    # Token was issued for a different cert.
    token = _mint_for_thumbprint(WRONG_THUMBPRINT)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/complaints",
            headers={"authorization": f"Bearer {token}"},
        )
    body = resp.json()
    assert resp.status_code == 401
    assert body["code"] == "SBS-401-023"
    assert body["type"].endswith("/TOKEN_CERT_THUMBPRINT_MISMATCH")


@pytest.mark.asyncio
async def test_token_sub_mismatches_mtls_institution(binding_settings, db_schema):
    """If somehow the token's sub claim is for a different institution
    than the mTLS-resolved one, the dependency rejects with the same
    thumbprint-mismatch shape (the binding is institution-equivalent).
    """

    await reset_engine_for_test()
    app = _make_app()
    token = _mint_for_thumbprint(BYPASS_THUMBPRINT, sub="SBS-009999")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.post(
            "/v1/complaints",
            headers={"authorization": f"Bearer {token}"},
        )
    body = resp.json()
    assert resp.status_code == 401
    assert body["code"] == "SBS-401-023"
