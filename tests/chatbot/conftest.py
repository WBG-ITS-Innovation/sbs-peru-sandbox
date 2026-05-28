"""Shared fixtures for the P-RESHAPE-9 chatbot suggestion tests."""

from __future__ import annotations

import pytest

SHARED = "sandbox-chatbot-suggestions-test-001"  # pragma: allowlist secret


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


def hdr(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {SHARED}", "X-SBS-Role": role}
