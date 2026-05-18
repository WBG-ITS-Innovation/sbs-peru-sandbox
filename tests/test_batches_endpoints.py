"""Tier 2 batch manifest endpoints — scaffolding only in Prompt 6.

Prompt 8 lands the upload pipeline; today the endpoints persist the
manifest, return a placeholder presigned URL, and emit an empty result
page.
"""

from __future__ import annotations

import hashlib

import pytest

from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


def _manifest() -> dict:
    return {
        "file_name": "BCO-2026-05.jsonl",
        "institution_id": "SBS-001234",
        "reporting_period_start": "2026-05-01",
        "reporting_period_end": "2026-05-31",
        "schema_version": "v0.1.0",
        "row_count": 412,
        "sha256": hashlib.sha256(b"placeholder").hexdigest(),
        "submitted_at": "2026-06-01T08:30:00+00:00",
    }


async def test_post_batch_manifest_returns_202(client):
    r = await client.post(
        "/v1/batches", json=_manifest(), headers={"Idempotency-Key": "b-1"}
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["batch_id"].startswith("batch_")
    assert body["status"] == "pending_upload"
    assert body["upload_url"].startswith("https://")
    # ETag is not a meaningful concept for the batch manifest yet.


async def test_get_batch_status_after_create(client):
    r1 = await client.post(
        "/v1/batches", json=_manifest(), headers={"Idempotency-Key": "b-2"}
    )
    batch_id = r1.json()["batch_id"]
    r2 = await client.get(f"/v1/batches/{batch_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["batch_id"] == batch_id
    assert body["status"] == "pending_upload"
    assert body["row_count_submitted"] == 412
    assert body["row_count_accepted"] == 0


async def test_get_batch_results_empty_until_prompt_8(client):
    r1 = await client.post(
        "/v1/batches", json=_manifest(), headers={"Idempotency-Key": "b-3"}
    )
    batch_id = r1.json()["batch_id"]
    r2 = await client.get(f"/v1/batches/{batch_id}/results")
    assert r2.status_code == 200
    body = r2.json()
    assert body["batch_id"] == batch_id
    assert body["rows"] == []
    assert body["next_cursor"] is None


async def test_post_batch_tenant_mismatch_404(client):
    bad = _manifest()
    bad["institution_id"] = "SBS-005678"
    r = await client.post(
        "/v1/batches", json=bad, headers={"Idempotency-Key": "b-4"}
    )
    assert r.status_code == 404


async def test_get_batch_404(client):
    # 32 alnum chars after the prefix matches the path-parameter pattern.
    r = await client.get("/v1/batches/batch_NOTPRESENT0000000000000000")
    assert r.status_code == 404
