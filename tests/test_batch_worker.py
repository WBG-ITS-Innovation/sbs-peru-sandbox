# SPDX-License-Identifier: Apache-2.0
"""arq batch worker — end-to-end happy path + mixed-row processing.

Calls ``process_batch`` directly (bypassing the arq daemon) against
the live testcontainer Postgres. Validates the state-machine
transition (pending → processing → complete), the
batch-row-rejections population, and the ``complaints.source='batch'``
write.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


_VALID_ROW_TEMPLATE = {
    "institution_id": "SBS-001234",
    "received_date": "2026-05-10",
    "complainant_doc_type": "DNI",
    "product_category": "TARJETA_CREDITO",
    "channel": "APP_MOVIL",
    "motivo_code": "COBRO_INDEBIDO",
    "severity": "HIGH",
    "description_text": "Cargo no autorizado por S/ 245.00 - pendiente revision.",
    "description_language": "es",
    "complainant_age_range": "35_44",
    "complainant_district": "150100",
    "submission_method": "APP_MOVIL",
    "original_reference_id": "",
    "resolution_status": "pendiente",
}


def _csv_from_rows(rows: list[dict[str, str]]) -> str:
    fields = ["complaint_id"] + list(_VALID_ROW_TEMPLATE.keys())
    lines = [",".join(fields)]
    for row in rows:
        merged = {"complaint_id": row["complaint_id"], **_VALID_ROW_TEMPLATE, **row}
        lines.append(",".join(str(merged[f]) for f in fields))
    return "\n".join(lines) + "\n"


def _manifest(csv_text: str, row_count: int) -> dict:
    return {
        "reporting_period_start": "2026-05-01",
        "reporting_period_end": "2026-05-31",
        "row_count_submitted": row_count,
        "checksum_sha256": hashlib.sha256(csv_text.encode("utf-8")).hexdigest(),
        "schema_version": "v0.1.0",
    }


async def _upload_batch(client, csv_text: str, *, idem: str) -> str:
    """Helper — upload via the live endpoint, return batch_id."""

    files = {
        "manifest": (
            None,
            json.dumps(_manifest(csv_text, csv_text.count("\n") - 1)),
            "application/json",
        ),
        "file": ("test.csv", csv_text.encode("utf-8"), "text/csv"),
    }
    r = await client.post(
        "/v1/batches", files=files, headers={"Idempotency-Key": idem}
    )
    assert r.status_code == 202, r.text
    return r.json()["batch_id"]


@pytest.mark.asyncio
async def test_process_batch_happy_path(client, test_database_url):
    csv_text = _csv_from_rows(
        [
            {"complaint_id": "BCO-2026-100100"},
            {"complaint_id": "BCO-2026-100101"},
            {"complaint_id": "BCO-2026-100102"},
        ]
    )
    batch_id = await _upload_batch(client, csv_text, idem="wkr-happy-1")

    # Run the worker function directly.
    from sbs_api.workers.batch_worker import process_batch

    result = await process_batch({"job_try": 1}, batch_id)
    assert result["status"] == "complete"
    assert result["row_count_accepted"] == 3
    assert result["row_count_rejected"] == 0

    # Status row reflects the terminal state.
    r = await client.get(f"/v1/batches/{batch_id}")
    body = r.json()
    assert body["status"] == "complete"
    assert body["row_count_accepted"] == 3
    assert body["row_count_rejected"] == 0
    assert body["completed_at"] is not None

    # Complaints visible via Tier 1 GET with source=batch.
    engine = create_async_engine(test_database_url)
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT complaint_id, source FROM complaints "
                "WHERE complaint_id LIKE 'BCO-2026-1001%' "
                "ORDER BY complaint_id"
            )
        )
        out = list(rows)
    await engine.dispose()
    assert len(out) == 3
    assert all(row[1] == "batch" for row in out)


@pytest.mark.asyncio
async def test_process_batch_mixed_rows(client, test_database_url):
    # First row valid; second row invalid (bad complainant_district pattern).
    csv_text = _csv_from_rows(
        [
            {"complaint_id": "BCO-2026-100200"},
            {
                "complaint_id": "BCO-2026-100201",
                "complainant_district": "XYZ",  # fails pattern \d{6}
            },
        ]
    )
    batch_id = await _upload_batch(client, csv_text, idem="wkr-mixed-1")

    from sbs_api.workers.batch_worker import process_batch

    result = await process_batch({"job_try": 1}, batch_id)
    assert result["status"] == "complete"
    assert result["row_count_accepted"] == 1
    assert result["row_count_rejected"] == 1

    # Rejection row is in batch_row_rejections.
    engine = create_async_engine(test_database_url)
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT row_index, field, rule, message "
                "FROM batch_row_rejections "
                "WHERE batch_id = :bid "
                "ORDER BY row_index, id"
            ),
            {"bid": batch_id},
        )
        rejections = list(rows)
    await engine.dispose()
    assert rejections, "expected at least one rejection row"
    # Row 1 is the bad row; one of the rejection records must point at
    # complainant_district.
    fields = {rec[1] for rec in rejections}
    assert any("complainant_district" in f for f in fields), fields


@pytest.mark.asyncio
async def test_process_batch_idempotent_on_terminal(client):
    csv_text = _csv_from_rows(
        [{"complaint_id": "BCO-2026-100300"}]
    )
    batch_id = await _upload_batch(client, csv_text, idem="wkr-term-1")

    from sbs_api.workers.batch_worker import process_batch

    first = await process_batch({"job_try": 1}, batch_id)
    assert first["status"] == "complete"
    # Replaying the job after terminal state must be a no-op.
    second = await process_batch({"job_try": 2}, batch_id)
    assert second["status"] == "complete"
    assert second["row_count_accepted"] == first["row_count_accepted"]


@pytest.mark.asyncio
async def test_process_batch_duplicate_complaint_id_within_batch(
    client, test_database_url
):
    """Two rows with the same complaint_id — first wins, second is rejected.

    Regression test for the SAVEPOINT-per-row pattern: a UNIQUE-constraint
    failure on row N must not poison the outer transaction.
    """

    csv_text = _csv_from_rows(
        [
            {"complaint_id": "BCO-2026-100500"},
            {"complaint_id": "BCO-2026-100500"},  # duplicate
            {"complaint_id": "BCO-2026-100501"},
        ]
    )
    batch_id = await _upload_batch(client, csv_text, idem="wkr-dup-1")

    from sbs_api.workers.batch_worker import process_batch

    result = await process_batch({"job_try": 1}, batch_id)
    assert result["status"] == "complete"
    assert result["row_count_accepted"] == 2
    assert result["row_count_rejected"] == 1

    # The duplicate row is recorded with rule='duplicate'.
    engine = create_async_engine(test_database_url)
    async with engine.connect() as conn:
        rejections = (
            await conn.execute(
                text(
                    "SELECT row_index, rule FROM batch_row_rejections "
                    "WHERE batch_id = :bid"
                ),
                {"bid": batch_id},
            )
        ).all()
    await engine.dispose()
    assert len(rejections) == 1
    assert rejections[0][1] == "duplicate"


@pytest.mark.asyncio
async def test_process_batch_missing_file_marks_failed(client, test_database_url):
    csv_text = _csv_from_rows(
        [{"complaint_id": "BCO-2026-100400"}]
    )
    batch_id = await _upload_batch(client, csv_text, idem="wkr-missing-1")

    # Delete the CSV on disk so the worker hits the not-found branch.
    from sbs_api.config import get_settings

    settings = get_settings()
    from pathlib import Path

    storage = Path(settings.batch_storage_path)
    if not storage.is_absolute():
        storage = (
            Path(__file__).resolve().parents[1]
            / settings.batch_storage_path
        )
    (storage / f"{batch_id}.csv").unlink()

    from sbs_api.workers.batch_worker import process_batch

    result = await process_batch({"job_try": 1}, batch_id)
    assert result["status"] == "failed"

    r = await client.get(f"/v1/batches/{batch_id}")
    body = r.json()
    assert body["status"] == "failed"
    assert body["failure_reason"] is not None
