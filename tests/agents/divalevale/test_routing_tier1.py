# SPDX-License-Identifier: Apache-2.0
"""DIValeVale Tier-1 routing + enrichment cycle (P-RESHAPE-8). DB-backed."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.agents.divalevale.agent import (
    fulfill_enrichment,
    validate_tier1_record,
)
from sbs_api.agents.providers.mock import MockProvider
from sbs_api.db.models.validation_audit import EnrichmentRequest, ValidationAudit
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


async def _sender_ok(req: httpx.Request) -> tuple[int, str]:
    return 200, "ok"


def _rec(**kw):
    base = {
        "complaint_id": "BCO-2026-000004",
        "institution_code": "BCO_DEMO_001",
        "captured_at": "2026-05-27T10:00:00Z",
        "motivo_code": "COBRO_INDEBIDO",
        "narrative_es": "x" * 40,
        "amount_claimed": 245.0,
        "currency": "PEN",
    }
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_valid_proceeds_to_triage(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            res = await validate_tier1_record(
                session, record=_rec(), sbs_institution_id="SBS-001234",
                provider=MockProvider(), sender=_sender_ok,
            )
            await session.commit()
    finally:
        await engine.dispose()
    assert res.verdict == "VALID"
    assert res.routing_action == "PROCEEDED_TO_TRIAGE"
    assert res.proceeds_to_triage is True


@pytest.mark.asyncio
async def test_insufficient_flags_for_enrichment_and_fires_webhook(
    test_database_url, db_schema
):
    sent: list[str] = []

    async def capture(req: httpx.Request) -> tuple[int, str]:
        sent.append(req.headers.get("X-Payload-Type", ""))
        return 200, "ok"

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            res = await validate_tier1_record(
                session,
                record=_rec(narrative_es="se me cobró mal", amount_claimed=None, currency=None),
                sbs_institution_id="SBS-001234",
                provider=MockProvider(),
                sender=capture,
            )
            await session.commit()

            reqs = (
                await session.execute(
                    select(EnrichmentRequest).where(
                        EnrichmentRequest.complaint_id == "BCO-2026-000004"
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    assert res.verdict == "INSUFFICIENT"
    assert res.routing_action == "FLAGGED_FOR_ENRICHMENT"
    assert res.proceeds_to_triage is False
    assert sent == ["VALIDATION_ENRICHMENT_REQUEST"]
    assert len(reqs) == 1
    assert reqs[0].state == "PENDING"
    assert reqs[0].delivery_status == "DELIVERED"


@pytest.mark.asyncio
async def test_invalid_is_rejected_not_stored_for_triage(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            res = await validate_tier1_record(
                session, record=_rec(motivo_code="NOPE"),
                sbs_institution_id="SBS-001234", provider=MockProvider(),
                sender=_sender_ok,
            )
            await session.commit()
    finally:
        await engine.dispose()
    assert res.verdict == "INVALID"
    assert res.routing_action == "REJECTED"
    assert res.proceeds_to_triage is False


@pytest.mark.asyncio
async def test_recoverable_then_recovered_proceeds(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            res = await validate_tier1_record(
                session,
                record=_rec(
                    narrative_es="Me cobraron S/ 245.00 sin aviso, reclamo formal.",
                    amount_claimed=None,
                    currency=None,
                ),
                sbs_institution_id="SBS-001234",
                provider=MockProvider(),
                sender=_sender_ok,
            )
            await session.commit()
    finally:
        await engine.dispose()
    # Amount recovered from narrative → re-run Pass1 → VALID → triage.
    assert res.recovered_record["amount_claimed"] == 245.0
    assert res.routing_action == "PROCEEDED_TO_TRIAGE"


@pytest.mark.asyncio
async def test_enrichment_fulfillment_marks_fulfilled(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            # First: flag for enrichment.
            await validate_tier1_record(
                session,
                record=_rec(narrative_es="se me cobró mal", amount_claimed=None, currency=None),
                sbs_institution_id="SBS-001234",
                provider=MockProvider(),
                sender=_sender_ok,
            )
            await session.commit()

            # FI resubmits an enriched record.
            res = await fulfill_enrichment(
                session,
                complaint_id="BCO-2026-000004",
                enriched_record=_rec(
                    narrative_es="Cargo no reconocido por S/ 245.00 el 12/05; solicito reversa.",
                ),
                sbs_institution_id="SBS-001234",
                provider=MockProvider(),
            )
            await session.commit()

            reqs = (
                await session.execute(
                    select(EnrichmentRequest).where(
                        EnrichmentRequest.complaint_id == "BCO-2026-000004"
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()
    assert res.proceeds_to_triage is True
    assert any(r.state == "FULFILLED" for r in reqs)


# --- cloud provider policy (changed in v0.2.0) ------------------------------
#
# This test previously asserted that DIValeVale rejects `cloud` unconditionally
# ("Cloud Pass-2 extraction is gated"). As of v0.2.0 cloud is admitted when BOTH
# a recorded legal approval and an active egress redaction layer are in place,
# because the redaction layer now guarantees no raw narrative leaves the
# process. The refusal is unchanged whenever either condition is missing, which
# is what these two tests pin.
#
# A stub carrying only `name` is used rather than a real CloudProvider: the gate
# reads the provider name, and constructing the real one needs Azure
# credentials that CI does not have.


class _CloudNamed:
    """Stand-in with the only attribute the gate reads."""

    name = "cloud"

    async def complete(self, *a, **k):  # pragma: no cover — must never be called
        raise AssertionError(
            "the gate should have refused before any completion was attempted"
        )


@pytest.mark.asyncio
async def test_cloud_provider_rejected_without_the_legal_approval(
    test_database_url, db_schema, monkeypatch
):
    """The default posture: no recorded approval, so cloud is refused.

    The refusal must happen before Pass 2 builds a prompt — hence the stub
    whose `complete` raises if it is ever reached.
    """
    from sbs_api.config import get_settings

    monkeypatch.setenv("SBS_API_CLOUD_LEGAL_APPROVED", "false")
    get_settings.cache_clear()

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            with pytest.raises(RuntimeError, match="requires BOTH"):
                await validate_tier1_record(
                    session, record=_rec(), sbs_institution_id="SBS-001234",
                    provider=_CloudNamed(),
                )
    finally:
        await engine.dispose()
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_cloud_provider_rejected_without_the_redaction_layer(
    test_database_url, db_schema, monkeypatch
):
    """Legal approval alone must not admit cloud — it would send raw text."""
    from sbs_api.agents.divalevale import agent as dv
    from sbs_api.config import get_settings

    monkeypatch.setenv("SBS_API_CLOUD_LEGAL_APPROVED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(dv, "redaction_layer_active", lambda: False)

    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            with pytest.raises(RuntimeError, match="redaction layer is not active"):
                await validate_tier1_record(
                    session, record=_rec(), sbs_institution_id="SBS-001234",
                    provider=_CloudNamed(),
                )
    finally:
        await engine.dispose()
        get_settings.cache_clear()


def test_cloud_provider_permitted_when_both_conditions_hold(monkeypatch):
    """The permitting direction, at the gate — no ingestion, no network."""
    from sbs_api.agents.divalevale.agent import _ensure_provider_permitted
    from sbs_api.config import get_settings

    monkeypatch.setenv("SBS_API_CLOUD_LEGAL_APPROVED", "true")
    get_settings.cache_clear()
    try:
        # redaction_layer_active() is deliberately not stubbed: the real
        # egress layer has to satisfy it.
        assert _ensure_provider_permitted(_CloudNamed()) is None
    finally:
        get_settings.cache_clear()
