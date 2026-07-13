# SPDX-License-Identifier: Apache-2.0
"""Circuit-breaker ingestion enforcement (P-RESHAPE-9).

When an FI's breaker is PAUSED, ingestion POSTs return 503 with reason
``fi_circuit_breaker_paused``; when NORMAL/absent, ingestion works.

Uses the root ``client`` fixture (institution auth chain bypassed,
institution_id=SBS-001234) and seeds the breaker row directly.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.db.models.fi_circuit_breaker import FiCircuitBreaker
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

_BASE_COMPLAINT: dict = {
    "complaint_id": "BCO-2026-000999",
    "institution_id": "SBS-001234",
    "received_date": "2026-05-12",
    "complainant_doc_type": "DNI",
    "product_category": "TARJETA_CREDITO",
    "channel": "APP_MOVIL",
    "motivo_code": "COBRO_INDEBIDO",
    "severity": "HIGH",
    "description_text": "Cargo no autorizado por S/ 245.00 — pendiente de revisión.",
    "description_language": "es",
    "complainant_age_range": "35_44",
    "complainant_district": "150100",
    "submission_method": "APP_MOVIL",
    "original_reference_id": None,
    "resolution_status": "pendiente",
}


async def _set_breaker(test_database_url: str, *, state: str | None) -> None:
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    async with SM() as session:
        await session.execute(
            delete(FiCircuitBreaker).where(
                FiCircuitBreaker.institution_code == "SBS-001234"
            )
        )
        if state is not None:
            session.add(
                FiCircuitBreaker(
                    institution_code="SBS-001234",
                    state=state,
                    set_by_user_id="itops",
                    rationale="x" * 50,
                )
            )
        await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_paused_fi_ingestion_returns_503(client, test_database_url):
    await _set_breaker(test_database_url, state="PAUSED")
    r = await client.post(
        "/v1/complaints",
        json={"complaint": _BASE_COMPLAINT},
        headers={"Idempotency-Key": "cb-paused-1"},
    )
    assert r.status_code == 503, r.text
    assert "fi_circuit_breaker_paused" in r.text


@pytest.mark.asyncio
async def test_resumed_fi_ingestion_succeeds(client, test_database_url):
    await _set_breaker(test_database_url, state="NORMAL")
    r = await client.post(
        "/v1/complaints",
        json={"complaint": _BASE_COMPLAINT},
        headers={"Idempotency-Key": "cb-normal-1"},
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_no_breaker_row_ingestion_succeeds(client, test_database_url):
    await _set_breaker(test_database_url, state=None)
    r = await client.post(
        "/v1/complaints",
        json={"complaint": _BASE_COMPLAINT},
        headers={"Idempotency-Key": "cb-absent-1"},
    )
    assert r.status_code == 201, r.text
