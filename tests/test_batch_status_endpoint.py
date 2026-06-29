# SPDX-License-Identifier: Apache-2.0
"""Tier 2 batch status endpoint — Workstream C.

Per-tenant binding, state visibility before and after the worker runs.
"""

from __future__ import annotations

import hashlib
import json

import pytest

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


async def test_status_visible_immediately_after_upload(client):
    csv_text = _csv_from_rows([{"complaint_id": "BCO-2026-200001"}])
    r1 = await client.post(
        "/v1/batches",
        files=_files(csv_text),
        headers={"Idempotency-Key": "stat-1"},
    )
    batch_id = r1.json()["batch_id"]

    r2 = await client.get(f"/v1/batches/{batch_id}")
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["batch_id"] == batch_id
    assert body["status"] == "pending"
    assert body["completed_at"] is None
    assert body["failure_reason"] is None


async def test_status_transitions_after_worker_run(client):
    csv_text = _csv_from_rows(
        [
            {"complaint_id": "BCO-2026-200010"},
            {"complaint_id": "BCO-2026-200011"},
        ]
    )
    r1 = await client.post(
        "/v1/batches",
        files=_files(csv_text),
        headers={"Idempotency-Key": "stat-2"},
    )
    batch_id = r1.json()["batch_id"]

    from sbs_api.workers.batch_worker import process_batch

    await process_batch({"job_try": 1}, batch_id)

    r2 = await client.get(f"/v1/batches/{batch_id}")
    body = r2.json()
    assert body["status"] == "complete"
    assert body["row_count_accepted"] == 2
    assert body["row_count_rejected"] == 0
    assert body["completed_at"] is not None


@pytest.mark.asyncio
async def test_status_cross_tenant_404(client, app):
    csv_text = _csv_from_rows([{"complaint_id": "BCO-2026-200020"}])
    r1 = await client.post(
        "/v1/batches",
        files=_files(csv_text),
        headers={"Idempotency-Key": "stat-3"},
    )
    batch_id = r1.json()["batch_id"]

    from sbs_api.auth.scopes import ALL_SCOPES
    from sbs_api.dependencies.oauth import (
        VerifiedToken,
        verified_oauth_token_with_scope,
    )

    other_token = VerifiedToken(
        institution_id="SBS-005678",
        granted_scopes=frozenset(ALL_SCOPES),
        cert_thumbprint="1" * 64,
    )

    async def _other_oauth() -> VerifiedToken:
        return other_token

    for scope in ALL_SCOPES:
        app.dependency_overrides[
            verified_oauth_token_with_scope(scope)
        ] = _other_oauth

    r2 = await client.get(f"/v1/batches/{batch_id}")
    assert r2.status_code == 404
