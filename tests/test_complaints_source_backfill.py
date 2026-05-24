"""Tier 1 POST writes `complaints.source = 'api_realtime'`.

The Tier 2 path writes ``source='batch'``; this test confirms the Tier 1
side of the dual-source invariant (ADR 0034). Pre-existing rows are
back-filled by the migration's server_default.
"""

from __future__ import annotations

import secrets

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


def _payload() -> dict:
    # Pattern ^[A-Z0-9]{1,4}-\d{4}-\d{6,10}$ — 6-10 digit suffix.
    suffix = str(secrets.randbelow(10_000_000_000)).zfill(10)
    return {
        "complaint": {
            "complaint_id": f"BCO-2026-{suffix}",
            "institution_id": "SBS-001234",
            "received_date": "2026-05-10",
            "complainant_doc_type": "DNI",
            "product_category": "TARJETA_CREDITO",
            "channel": "APP_MOVIL",
            "motivo_code": "COBRO_INDEBIDO",
            "severity": "HIGH",
            "description_text": "Cargo no autorizado por S/ 245.00.",
            "description_language": "es",
            "complainant_age_range": "35_44",
            "complainant_district": "150100",
            "submission_method": "APP_MOVIL",
            "original_reference_id": None,
            "resolution_status": "pendiente",
        }
    }


async def test_existing_rows_default_to_api_realtime(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT complaint_id, source FROM complaints "
                "WHERE complaint_id LIKE 'BCO-2026-%'"
            )
        )
        rows = {row[0]: row[1] for row in result}
        coopac = (
            await conn.execute(
                text(
                    "SELECT DISTINCT source FROM complaints "
                    "WHERE complaint_id LIKE 'COP-2026-%'"
                )
            )
        ).scalars().all()
    await engine.dispose()
    # The fixture seeds three BCO Tier 1 rows on SBS-001234; all must
    # default to api_realtime via the migration server_default. The
    # Tier 2 COP rows are seeded explicitly with source='batch' and
    # are checked separately below.
    assert rows, "expected at least one BCO-2026-* row from the fixture"
    assert set(rows.values()) == {"api_realtime"}, rows
    assert set(coopac) == {"batch"}, coopac


async def test_tier_1_post_writes_api_realtime(client, test_database_url):
    payload = _payload()
    r = await client.post(
        "/v1/complaints",
        json=payload,
        headers={"Idempotency-Key": "src-1"},
    )
    assert r.status_code == 201, r.text

    engine = create_async_engine(test_database_url)
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT source FROM complaints WHERE complaint_id = :cid"
            ),
            {"cid": payload["complaint"]["complaint_id"]},
        )
        row = result.scalar_one()
    await engine.dispose()
    assert row == "api_realtime"
