# SPDX-License-Identifier: Apache-2.0
"""Tier 2 batch endpoint — Workstream A (ADR 0034).

Multipart upload happy/sad paths against the standard auth-bypass app
fixture. The HMAC body-hash and rate-limiter behaviours live in
:mod:`tests.test_batch_multipart_streaming` and the smoke test
respectively.
"""

from __future__ import annotations

import hashlib
import json

from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


_CSV = (
    "complaint_id,institution_id,received_date\n"
    "BCO-2026-100001,SBS-001234,2026-05-10\n"
    "BCO-2026-100002,SBS-001234,2026-05-11\n"
)


def _manifest(checksum: str | None = None) -> dict:
    return {
        "reporting_period_start": "2026-05-01",
        "reporting_period_end": "2026-05-31",
        "row_count_submitted": 2,
        "checksum_sha256": checksum
        or hashlib.sha256(_CSV.encode("utf-8")).hexdigest(),
        "schema_version": "v0.1.0",
    }


def _files(csv: bytes = _CSV.encode("utf-8")) -> dict:
    return {
        "manifest": (None, json.dumps(_manifest()), "application/json"),
        "file": ("test.csv", csv, "text/csv"),
    }


async def test_post_batch_returns_202_with_location(client):
    r = await client.post(
        "/v1/batches",
        files=_files(),
        headers={"Idempotency-Key": "b-happy-1"},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["batch_id"].startswith("batch_")
    assert body["status"] == "pending"
    assert "Location" in r.headers
    assert r.headers["Location"] == f"/v1/batches/{body['batch_id']}"


async def test_post_batch_persists_row_with_correct_state(client):
    r1 = await client.post(
        "/v1/batches",
        files=_files(),
        headers={"Idempotency-Key": "b-state-1"},
    )
    batch_id = r1.json()["batch_id"]

    r2 = await client.get(f"/v1/batches/{batch_id}")
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["batch_id"] == batch_id
    assert body["status"] == "pending"
    assert body["row_count_submitted"] == 2
    assert body["row_count_accepted"] == 0
    assert body["row_count_rejected"] == 0


async def test_post_batch_checksum_mismatch_returns_400(client):
    bogus = "0" * 64
    files = {
        "manifest": (
            None,
            json.dumps(_manifest(checksum=bogus)),
            "application/json",
        ),
        "file": ("test.csv", _CSV.encode("utf-8"), "text/csv"),
    }
    r = await client.post(
        "/v1/batches", files=files, headers={"Idempotency-Key": "b-csum-1"}
    )
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["code"] == "SBS-400-007"


async def test_post_batch_invalid_manifest_returns_400(client):
    # Reporting period inverted.
    bad_manifest = _manifest()
    bad_manifest["reporting_period_start"] = "2026-12-31"
    bad_manifest["reporting_period_end"] = "2026-01-01"
    files = {
        "manifest": (None, json.dumps(bad_manifest), "application/json"),
        "file": ("test.csv", _CSV.encode("utf-8"), "text/csv"),
    }
    r = await client.post(
        "/v1/batches", files=files, headers={"Idempotency-Key": "b-mani-1"}
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "SBS-400-006"


async def test_post_batch_malformed_manifest_returns_400(client):
    files = {
        "manifest": (None, "{not-json", "application/json"),
        "file": ("test.csv", _CSV.encode("utf-8"), "text/csv"),
    }
    r = await client.post(
        "/v1/batches", files=files, headers={"Idempotency-Key": "b-mani-2"}
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "SBS-400-006"


async def test_get_batch_status_cross_tenant_404(client, app):
    # Switch the OAuth override to a different institution and confirm the
    # batch created by the first one is not visible.
    r1 = await client.post(
        "/v1/batches",
        files=_files(),
        headers={"Idempotency-Key": "b-tenant-1"},
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
        dep = verified_oauth_token_with_scope(scope)
        app.dependency_overrides[dep] = _other_oauth

    r2 = await client.get(f"/v1/batches/{batch_id}")
    assert r2.status_code == 404


async def test_post_batch_oversized_returns_413(client, monkeypatch):
    # Shrink the cap so we can trigger the 413 without allocating a
    # multi-megabyte buffer in the test.
    from sbs_api.config import get_settings

    monkeypatch.setenv("SBS_API_MAX_BATCH_FILE_BYTES", "1024")
    get_settings.cache_clear()
    try:
        # Build a CSV larger than 1 KB. The multipart envelope adds a
        # few hundred bytes of headers + boundary, so 2 KB of body is
        # comfortably over.
        big_csv = (
            "complaint_id,institution_id,received_date\n"
            + ("BCO-2026-100001,SBS-001234,2026-05-10\n" * 80)
        )
        files = {
            "manifest": (
                None,
                json.dumps(
                    {
                        **_manifest(),
                        "checksum_sha256": hashlib.sha256(
                            big_csv.encode("utf-8")
                        ).hexdigest(),
                    }
                ),
                "application/json",
            ),
            "file": ("big.csv", big_csv.encode("utf-8"), "text/csv"),
        }
        r = await client.post(
            "/v1/batches",
            files=files,
            headers={"Idempotency-Key": "b-oversize-1"},
        )
        assert r.status_code == 413, r.text
        body = r.json()
        assert body["code"] == "SBS-413-002"
        assert body["type"].endswith("/BATCH_FILE_TOO_LARGE")
    finally:
        get_settings.cache_clear()
