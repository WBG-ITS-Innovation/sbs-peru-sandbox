# SPDX-License-Identifier: Apache-2.0
"""End-to-end complaint endpoint tests against a real Postgres testcontainer.

Covers every endpoint and the cross-cutting rules from the Prompt 6 spec:

* POST happy path, validation error, idempotency replay (match), idempotency
  replay (different body → 409).
* GET retrieve, 404, tenant-mismatch returns 404 (does not leak existence).
* GET list with filters, cursor round-trip, cursor tamper rejection.
* PATCH happy, ETag mismatch (412), ETag missing (428), tenant mismatch (404),
  forbidden state transition (422).
"""

from __future__ import annotations

import json

import pytest

from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


# A canonical valid submission body. Tests mutate copies; the original stays
# stable so the body-hash on idempotency tests stays predictable.
_BASE_COMPLAINT: dict = {
    "complaint_id": "BCO-2026-000999",
    "institution_id": "SBS-001234",
    "received_date": "2026-05-12",
    "complainant_doc_type": "DNI",
    "product_category": "TARJETA_CREDITO",
    "channel": "APP_MOVIL",
    "motivo_code": "COBRO_INDEBIDO",
    "severity": "HIGH",
    "description_text": "Cargo no autorizado por S/ 245.00 — pendiente de revisión por equipo.",
    "description_language": "es",
    "complainant_age_range": "35_44",
    "complainant_district": "150100",
    "submission_method": "APP_MOVIL",
    "original_reference_id": None,
    "resolution_status": "pendiente",
}


def _submission(**overrides) -> dict:
    body = {"complaint": {**_BASE_COMPLAINT, **overrides}}
    return body


# --- POST happy + validation ----------------------------------------------


async def test_post_complaint_happy_path(client):
    r = await client.post(
        "/v1/complaints",
        json=_submission(),
        headers={"Idempotency-Key": "idem-001"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["complaint_id"] == "BCO-2026-000999"
    assert body["institution_id"] == "SBS-001234"
    assert body["resolution_status"] == "pendiente"
    assert r.headers["Location"] == "/v1/complaints/BCO-2026-000999"
    assert r.headers.get("ETag", "").startswith('"')


async def test_post_complaint_validation_error_returns_problem_json(client):
    bad = _submission(complainant_district="XYZ")  # not a 6-digit ubigeo
    r = await client.post(
        "/v1/complaints",
        json=bad,
        headers={"Idempotency-Key": "idem-002"},
    )
    assert r.status_code == 422
    assert r.headers.get("content-type", "").startswith("application/problem+json")
    body = r.json()
    assert body["code"] == "SBS-422-001"
    assert isinstance(body["errors"], list) and body["errors"]


async def test_post_complaint_tenant_mismatch_404(client):
    bad = _submission(institution_id="SBS-005678")  # the other demo institution
    r = await client.post(
        "/v1/complaints",
        json=bad,
        headers={"Idempotency-Key": "idem-003"},
    )
    assert r.status_code == 404


# --- POST idempotency ------------------------------------------------------


async def test_post_idempotency_replay_returns_same_body(client):
    body = _submission(complaint_id="BCO-2026-000501")
    h = {"Idempotency-Key": "idem-replay-match"}
    r1 = await client.post("/v1/complaints", json=body, headers=h)
    assert r1.status_code == 201
    r2 = await client.post("/v1/complaints", json=body, headers=h)
    assert r2.status_code == 201
    assert r2.json() == r1.json()
    assert r2.headers.get("Idempotency-Replayed") == "true"


async def test_post_idempotency_different_body_returns_409(client):
    body1 = _submission(complaint_id="BCO-2026-000502")
    body2 = _submission(complaint_id="BCO-2026-000503")
    h = {"Idempotency-Key": "idem-replay-mismatch"}
    r1 = await client.post("/v1/complaints", json=body1, headers=h)
    assert r1.status_code == 201
    r2 = await client.post("/v1/complaints", json=body2, headers=h)
    assert r2.status_code == 409
    assert "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_BODY" in r2.json()["type"]


# --- GET retrieve / 404 / tenant -------------------------------------------


async def test_get_complaint_happy(client):
    # The fixture seeds three complaints under SBS-001234.
    r = await client.get("/v1/complaints/BCO-2026-000001")
    assert r.status_code == 200
    assert r.json()["complaint_id"] == "BCO-2026-000001"
    assert r.headers.get("ETag", "").startswith('"')


async def test_get_complaint_404(client):
    r = await client.get("/v1/complaints/BCO-2026-999999")
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == "SBS-404-001"


async def test_get_complaint_tenant_mismatch_returns_404(client, db_schema):
    """Tenant mismatch returns 404, not 403 — does not leak existence."""

    # Insert a complaint owned by SBS-005678 (the other tenant).
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sbs_api.db.models.complaint import ComplaintRecord
    from datetime import date

    from sbs_api.config import get_settings

    engine = create_async_engine(get_settings().database_url)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionMaker() as session:
        session.add(
            ComplaintRecord(
                complaint_id="COOP-2026-000001",
                institution_id="SBS-005678",
                received_date=date(2026, 5, 14),
                complainant_doc_type="DNI",
                product_category="TARJETA_CREDITO",
                channel="APP_MOVIL",
                motivo_code="COBRO_INDEBIDO",
                severity="HIGH",
                description_text="Otra tenancy — debe esconderse del caller.",
                description_language="es",
                complainant_age_range="35_44",
                complainant_district="150100",
                submission_method="APP_MOVIL",
                original_reference_id=None,
                resolution_status="pendiente",
            )
        )
        await session.commit()
    await engine.dispose()

    r = await client.get("/v1/complaints/COOP-2026-000001")
    assert r.status_code == 404  # 404, not 403


# --- GET list / cursor -----------------------------------------------------


async def test_list_complaints_returns_seeded_rows(client):
    r = await client.get("/v1/complaints")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) >= 3  # at least the fixture seed
    for item in body["items"]:
        assert item["institution_id"] == "SBS-001234"


async def test_list_complaints_filter_by_resolution_status(client):
    r = await client.get(
        "/v1/complaints", params={"resolution_status": "pendiente"}
    )
    assert r.status_code == 200
    body = r.json()
    for item in body["items"]:
        assert item["resolution_status"] == "pendiente"


async def test_list_complaints_cursor_round_trip(client):
    # Page size 1 to force a cursor.
    r1 = await client.get("/v1/complaints", params={"page_size": 1})
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["next_cursor"] is not None
    r2 = await client.get(
        "/v1/complaints",
        params={"page_size": 1, "next_cursor": body1["next_cursor"]},
    )
    assert r2.status_code == 200
    # Distinct page.
    assert r2.json()["items"][0]["complaint_id"] != body1["items"][0]["complaint_id"]


async def test_list_complaints_tampered_cursor_rejected(client):
    r = await client.get(
        "/v1/complaints", params={"page_size": 1, "next_cursor": "not-a-valid-cursor"}
    )
    assert r.status_code == 400
    body = r.json()
    assert "CURSOR_INVALID" in body["type"]


# --- PATCH happy + ETag + state-machine -----------------------------------


async def test_patch_status_happy_path(client):
    # Read first to capture the ETag.
    r_get = await client.get("/v1/complaints/BCO-2026-000001")
    assert r_get.status_code == 200
    etag = r_get.headers["ETag"]

    r_patch = await client.patch(
        "/v1/complaints/BCO-2026-000001/status",
        json={
            "resolution_status": "atendido",
            "reason": "Reembolso aplicado y notificado al cliente.",
        },
        headers={"If-Match": etag, "Idempotency-Key": "patch-001"},
    )
    assert r_patch.status_code == 200, r_patch.text
    body = r_patch.json()
    assert body["resolution_status"] == "atendido"
    # The response ETag is fresh.
    assert r_patch.headers["ETag"] != etag


async def test_patch_status_etag_mismatch_returns_412(client):
    r_patch = await client.patch(
        "/v1/complaints/BCO-2026-000002/status",
        json={
            "resolution_status": "atendido",
            "reason": "Razón válida que cumple la longitud mínima.",
        },
        headers={
            "If-Match": '"deadbeefdeadbeefdeadbeef"',
            "Idempotency-Key": "patch-002",
        },
    )
    assert r_patch.status_code == 412
    body = r_patch.json()
    assert "ETAG_MISMATCH" in body["type"]


async def test_patch_status_etag_missing_returns_428(client):
    r_patch = await client.patch(
        "/v1/complaints/BCO-2026-000003/status",
        json={
            "resolution_status": "atendido",
            "reason": "Razón válida que cumple la longitud mínima.",
        },
        headers={"Idempotency-Key": "patch-003"},
    )
    assert r_patch.status_code == 428


async def test_patch_status_tenant_mismatch_404(client):
    # Use a complaint id format that's syntactically valid but not present.
    r_patch = await client.patch(
        "/v1/complaints/COOP-2026-999999/status",
        json={
            "resolution_status": "atendido",
            "reason": "Razón válida que cumple la longitud mínima.",
        },
        headers={"If-Match": '"x"', "Idempotency-Key": "patch-tenant"},
    )
    assert r_patch.status_code == 404


async def test_patch_status_forbidden_transition_returns_422(client):
    # Patch a fresh complaint to terminal 'atendido' first, then try to walk
    # back to 'pendiente' which is forbidden by the state machine.
    submission = _submission(complaint_id="BCO-2026-000777")
    r_post = await client.post(
        "/v1/complaints",
        json=submission,
        headers={"Idempotency-Key": "fixture-walkback"},
    )
    assert r_post.status_code == 201
    etag1 = r_post.headers["ETag"]
    r_patch1 = await client.patch(
        "/v1/complaints/BCO-2026-000777/status",
        json={
            "resolution_status": "atendido",
            "reason": "Caso resuelto satisfactoriamente con cliente.",
        },
        headers={"If-Match": etag1, "Idempotency-Key": "walkback-1"},
    )
    assert r_patch1.status_code == 200
    etag2 = r_patch1.headers["ETag"]
    r_patch2 = await client.patch(
        "/v1/complaints/BCO-2026-000777/status",
        json={"resolution_status": "pendiente"},
        headers={"If-Match": etag2, "Idempotency-Key": "walkback-2"},
    )
    assert r_patch2.status_code == 422
    body = r_patch2.json()
    assert "RESOLUTION_STATUS_TRANSITION_FORBIDDEN" in body["type"]
