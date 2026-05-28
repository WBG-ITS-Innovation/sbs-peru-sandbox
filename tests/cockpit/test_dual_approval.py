"""Sector-broadcast dual approval (P-RESHAPE-6).

Enforces: cannot deliver with only one approver; primary + secondary
must be distinct users; both require a 50-char rationale; the
Superintendent CAN co-approve as the secondary (the explicit
read-only exception); a plain analyst cannot approve at all.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.auth.persona_scopes import (
    ROLE_ANALYST,
    ROLE_SUPERINTENDENT,
    ROLE_SUPERVISOR,
    ROLE_UNIT_HEAD,
)
from sbs_api.db.models.sector_broadcast import SectorBroadcast
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

SHARED_VAL = "sandbox-dual-approval-test-001"  # pragma: allowlist secret
NOW = datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc)
RATIONALE = "Confirmada la campaña de fraude; corresponde alertar al sector ahora."


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


def _hdr(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {SHARED_VAL}", "X-SBS-Role": role}


async def _seed_broadcast(test_database_url: str, status="AWAITING_DUAL_APPROVAL") -> str:
    from sbs_api.db.models.pattern_detection import PatternDetection

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    pattern_id = str(uuid.uuid4())
    broadcast_id = str(uuid.uuid4())
    async with SM() as session:
        session.add(
            PatternDetection(
                pattern_id=pattern_id,
                detected_at=NOW,
                window_start=NOW - timedelta(hours=72),
                window_end=NOW,
                institution_code="SBS-001234",
                complaint_category="FRAUD",
                pattern_type="FRAUD_EMERGENCE",
                severity_score=0.88,
                severity_band="HIGH",
                contributing_complaint_ids=["FR-1"],
                contributing_indecopi_case_ids=None,
                composite_breakdown={},
                triggered_investigation=True,
            )
        )
        await session.flush()
        session.add(
            SectorBroadcast(
                broadcast_id=broadcast_id,
                origin_pattern_id=pattern_id,
                origin_fi_anonymized=True,
                target_fi_codes=[f"SBS-10{i:04d}" for i in range(1, 5)],
                status=status,
                threat_summary_es="Amenaza generica.",
                threat_summary_en="Generic threat.",
                threat_indicators=["PHISHING_KEYWORD"],
                suggested_controls=["STRENGTHEN_FRAUD_MONITORING"],
                urgency="ELEVATED",
                response_deadline=NOW + timedelta(days=5),
                requires_dual_approval=True,
                model_id="m",
                model_provider="template",
            )
        )
        await session.commit()
    await engine.dispose()
    return broadcast_id


@pytest.mark.asyncio
async def test_analyst_cannot_approve_primary(app_with_secret, test_database_url):
    bid = await _seed_broadcast(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            f"/v1/internal/sector_broadcast/{bid}/approve_primary",
            json={"actor_id": "lucia", "rationale": RATIONALE},
            headers=_hdr(ROLE_ANALYST),
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_primary_requires_50_char_rationale(app_with_secret, test_database_url):
    bid = await _seed_broadcast(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            f"/v1/internal/sector_broadcast/{bid}/approve_primary",
            json={"actor_id": "maria", "rationale": "muy corto"},
            headers=_hdr(ROLE_SUPERVISOR),
        )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_secondary_must_differ_from_primary(app_with_secret, test_database_url):
    bid = await _seed_broadcast(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        p = await c.post(
            f"/v1/internal/sector_broadcast/{bid}/approve_primary",
            json={"actor_id": "jorge", "rationale": RATIONALE},
            headers=_hdr(ROLE_UNIT_HEAD),
        )
        assert p.status_code == 201
        # Same user tries to also be the secondary → 409.
        s = await c.post(
            f"/v1/internal/sector_broadcast/{bid}/approve_secondary",
            json={"actor_id": "jorge", "rationale": RATIONALE},
            headers=_hdr(ROLE_UNIT_HEAD),
        )
    assert s.status_code == 409


@pytest.mark.asyncio
async def test_superintendent_can_co_approve_secondary(
    app_with_secret, test_database_url
):
    """The explicit Sergio exception: Superintendent co-approves as the
    secondary, completing dual approval → delivery runs."""
    bid = await _seed_broadcast(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        p = await c.post(
            f"/v1/internal/sector_broadcast/{bid}/approve_primary",
            json={"actor_id": "maria", "rationale": RATIONALE},
            headers=_hdr(ROLE_SUPERVISOR),
        )
        assert p.status_code == 201
        assert p.json()["status"] == "AWAITING_SECONDARY_APPROVAL"

        s = await c.post(
            f"/v1/internal/sector_broadcast/{bid}/approve_secondary",
            json={"actor_id": "sergio", "rationale": RATIONALE},
            headers=_hdr(ROLE_SUPERINTENDENT),
        )
    assert s.status_code == 201
    # Delivery target unreachable in tests → DELIVERED or PARTIALLY.
    assert s.json()["status"] in {"DELIVERED", "PARTIALLY_DELIVERED"}

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            b = await session.get(SectorBroadcast, bid)
    finally:
        await engine.dispose()
    assert b.primary_approver == "maria"
    assert b.secondary_approver == "sergio"


@pytest.mark.asyncio
async def test_cannot_secondary_before_primary(app_with_secret, test_database_url):
    bid = await _seed_broadcast(test_database_url)
    transport = ASGITransport(app=app_with_secret)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        s = await c.post(
            f"/v1/internal/sector_broadcast/{bid}/approve_secondary",
            json={"actor_id": "sergio", "rationale": RATIONALE},
            headers=_hdr(ROLE_SUPERINTENDENT),
        )
    assert s.status_code == 409  # still AWAITING_DUAL_APPROVAL
