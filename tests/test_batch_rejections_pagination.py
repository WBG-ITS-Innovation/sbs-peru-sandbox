"""Tier 2 batch rejections — Workstream C signed-cursor pagination.

Posts a batch with multiple invalid rows, runs the worker, then walks
the /rejections endpoint with page_size=1 to assert keyset semantics
and the CURSOR_INVALID branch.
"""

from __future__ import annotations

import hashlib
import json

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
    "description_text": "Cargo no autorizado por S/ 245.00 - pendiente.",
    "description_language": "es",
    "complainant_age_range": "35_44",
    "complainant_district": "150100",
    "submission_method": "APP_MOVIL",
    "original_reference_id": "",
    "resolution_status": "pendiente",
}


def _csv_from_rows(rows):
    fields = ["complaint_id"] + list(_VALID_ROW_TEMPLATE.keys())
    lines = [",".join(fields)]
    for row in rows:
        merged = {"complaint_id": row["complaint_id"], **_VALID_ROW_TEMPLATE, **row}
        lines.append(",".join(str(merged[f]) for f in fields))
    return "\n".join(lines) + "\n"


def _files(csv_text: str) -> dict:
    return {
        "manifest": (
            None,
            json.dumps(
                {
                    "reporting_period_start": "2026-05-01",
                    "reporting_period_end": "2026-05-31",
                    "row_count_submitted": csv_text.count("\n") - 1,
                    "checksum_sha256": hashlib.sha256(
                        csv_text.encode("utf-8")
                    ).hexdigest(),
                    "schema_version": "v0.1.0",
                }
            ),
            "application/json",
        ),
        "file": ("test.csv", csv_text.encode("utf-8"), "text/csv"),
    }


async def _upload_and_process(client, csv_text: str, idem: str) -> str:
    r = await client.post(
        "/v1/batches",
        files=_files(csv_text),
        headers={"Idempotency-Key": idem},
    )
    batch_id = r.json()["batch_id"]
    from sbs_api.workers.batch_worker import process_batch

    await process_batch({"job_try": 1}, batch_id)
    return batch_id


async def test_rejections_returned_with_field_detail(client):
    # Three rows, all with bad complainant_district pattern.
    csv_text = _csv_from_rows(
        [
            {"complaint_id": "BCO-2026-300001", "complainant_district": "AAA"},
            {"complaint_id": "BCO-2026-300002", "complainant_district": "BBB"},
            {"complaint_id": "BCO-2026-300003", "complainant_district": "CCC"},
        ]
    )
    batch_id = await _upload_and_process(client, csv_text, idem="rej-1")

    r = await client.get(f"/v1/batches/{batch_id}/rejections")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["batch_id"] == batch_id
    assert len(body["rejections"]) == 3
    # Each entry has the expected shape.
    for entry in body["rejections"]:
        assert isinstance(entry["row_index"], int)
        assert "complainant_district" in (entry["field"] or "")
        assert entry["rule"] != ""
        assert entry["message"] != ""
    assert body["next_cursor"] is None


async def test_rejections_pagination_walks_pages(client):
    csv_text = _csv_from_rows(
        [
            {"complaint_id": "BCO-2026-300010", "complainant_district": "AAA"},
            {"complaint_id": "BCO-2026-300011", "complainant_district": "BBB"},
            {"complaint_id": "BCO-2026-300012", "complainant_district": "CCC"},
        ]
    )
    batch_id = await _upload_and_process(client, csv_text, idem="rej-2")

    # page_size=1 — three pages expected.
    seen_indexes: list[int] = []
    cursor = None
    pages = 0
    while True:
        params = {"page_size": 1}
        if cursor is not None:
            params["next_cursor"] = cursor
        r = await client.get(
            f"/v1/batches/{batch_id}/rejections", params=params
        )
        assert r.status_code == 200, r.text
        body = r.json()
        seen_indexes.extend(
            entry["row_index"] for entry in body["rejections"]
        )
        cursor = body["next_cursor"]
        pages += 1
        if cursor is None:
            break
        assert pages < 10, "pagination did not terminate"
    assert sorted(seen_indexes) == [0, 1, 2]
    assert pages == 3


async def test_rejections_tampered_cursor_returns_400(client):
    csv_text = _csv_from_rows(
        [
            {"complaint_id": "BCO-2026-300020", "complainant_district": "AAA"},
        ]
    )
    batch_id = await _upload_and_process(client, csv_text, idem="rej-3")

    r = await client.get(
        f"/v1/batches/{batch_id}/rejections",
        params={"next_cursor": "not-a-real-cursor"},
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["code"] == "SBS-400-005"


async def test_rejections_empty_when_no_failures(client):
    csv_text = _csv_from_rows(
        [{"complaint_id": "BCO-2026-300030"}]
    )
    batch_id = await _upload_and_process(client, csv_text, idem="rej-4")

    r = await client.get(f"/v1/batches/{batch_id}/rejections")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rejections"] == []
    assert body["next_cursor"] is None
