"""Explanation registry coverage (P-RESHAPE-5).

Every registered surface_id resolves to an ES + EN explanation with
provenance. At least 12 entries (acceptance criterion). The endpoint
404s on an unknown surface_id.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from sbs_api.routes.explain import EXPLANATIONS
from tests.conftest import pytestmark_db

SHARED_VAL = "sandbox-explain-test-001"  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# Pure registry checks (no DB)
# ---------------------------------------------------------------------------


def test_at_least_12_surfaces_registered():
    assert len(EXPLANATIONS) >= 12


def test_every_surface_has_es_en_and_provenance_keys():
    for surface_id, entry in EXPLANATIONS.items():
        assert entry["es"], f"{surface_id} missing ES"
        assert entry["en"], f"{surface_id} missing EN"
        assert len(entry["es"]) > 20, f"{surface_id} ES too short"
        # Provenance keys present (values may be None for non-agent surfaces).
        assert "source_agent" in entry
        assert "source_rule" in entry
        assert "source_data_window" in entry


def test_key_surfaces_present():
    for required in (
        "severity_band",
        "percentile",
        "z_score",
        "system_signal",
        "forecast_trend_direction",
        "fi_brief_remediation_areas",
        "cohort_assignment",
        "cloud_routing_zero",
    ):
        assert required in EXPLANATIONS


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

pytestmark = pytestmark_db


@pytest.fixture
async def app_with_secret(app_settings, monkeypatch, db_schema):
    monkeypatch.setenv("SBS_API_INTERNAL_API_SECRET", SHARED_VAL)
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


def _hdr() -> dict[str, str]:
    return {"Authorization": f"Bearer {SHARED_VAL}"}


@pytest.mark.asyncio
async def test_every_surface_id_resolves_over_http(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        listing = await c.get("/v1/internal/explain", headers=_hdr())
        assert listing.status_code == 200
        surface_ids = listing.json()["surface_ids"]
        assert len(surface_ids) >= 12
        for sid in surface_ids:
            r = await c.get(f"/v1/internal/explain/{sid}", headers=_hdr())
            assert r.status_code == 200, sid
            body = r.json()
            assert body["es"] and body["en"]


@pytest.mark.asyncio
async def test_unknown_surface_id_404(app_with_secret):
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/v1/internal/explain/not_a_real_surface", headers=_hdr())
    assert r.status_code == 404
