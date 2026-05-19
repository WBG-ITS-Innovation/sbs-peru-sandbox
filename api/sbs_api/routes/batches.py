"""Tier 2 batch endpoints — manifest scaffolding only in this prompt.

Prompt 8 lands the full processing pipeline; the routes here:

* Accept a manifest, persist it, return a presigned-style placeholder URL.
* Return the batch state (counts always zero in this prompt; Prompt 8 fills them).
* Return an empty result page until Prompt 8 wires per-row processing.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import uuid_utils as uuid7
from fastapi import APIRouter, Depends, Header, Path, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.session import get_sessionmaker
from sbs_api.dependencies.auth import AuthContext, get_auth_context
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.idempotency import (
    claim_idempotency_slot,
    get_idempotency_context,
    mark_complete,
)
from sbs_api.db.models.batch import BatchRecord
from sbs_api.errors.exceptions import IdempotencyKeyInFlight, ResourceNotFound
from sbs_api.models.requests import BatchManifest
from sbs_api.models.responses import (
    BatchResultsResponse,
    BatchStatus,
    BatchSubmission,
)

router = APIRouter(tags=["Ingestion (Tier 2)"])

_BATCH_ID_PREFIX = "batch_"


def _new_batch_id() -> str:
    # UUID v7 hex + 4 random hex chars for additional entropy. 32 chars total.
    base = str(uuid7.uuid7()).replace("-", "")
    return f"{_BATCH_ID_PREFIX}{base[:24]}{secrets.token_hex(2)}"


@router.post("/batches", status_code=202, response_model=BatchSubmission)
async def create_batch_manifest(
    request: Request,
    manifest: BatchManifest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    auth: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    if manifest.institution_id != auth.institution_id:
        raise ResourceNotFound(
            detail="institution_id in manifest does not match the authenticated caller."
        )
    body_bytes = await request.body()
    ctx = get_idempotency_context(
        institution_id=auth.institution_id,
        key=idempotency_key,
        body=body_bytes,
        method=request.method,
        path=request.url.path,
    )
    claim = await claim_idempotency_slot(get_sessionmaker(), ctx)
    if claim.state == "in_flight":
        raise IdempotencyKeyInFlight(
            detail=(
                "Another batch upload with this Idempotency-Key is "
                "still processing. Retry in a moment."
            ),
            extra_headers={"Retry-After": "1"},
        )
    if claim.state == "replay":
        import json as _json
        assert claim.record is not None
        cached_body = _json.loads(claim.record.response_payload)
        cached_headers = _json.loads(claim.record.response_headers)
        cached_headers["Idempotency-Replayed"] = "true"
        return JSONResponse(
            status_code=claim.record.response_status,
            content=cached_body,
            headers=cached_headers,
        )

    batch_id = _new_batch_id()
    record = BatchRecord(
        batch_id=batch_id,
        institution_id=manifest.institution_id,
        file_name=manifest.file_name,
        reporting_period_start=manifest.reporting_period_start,
        reporting_period_end=manifest.reporting_period_end,
        schema_version=manifest.schema_version,
        row_count_submitted=manifest.row_count,
        sha256=manifest.sha256,
        status="pending_upload",
    )
    session.add(record)
    await session.flush()

    submission = BatchSubmission(
        batch_id=batch_id,
        upload_url=f"https://sandbox.sbs.gob.pe/uploads/{batch_id}",  # placeholder; Prompt 8 wires real presigning
        upload_expires_at=datetime.now(timezone.utc) + timedelta(minutes=60),
        status="pending_upload",
    )
    body = submission.model_dump(mode="json")
    headers: dict[str, str] = {}
    await mark_complete(session, ctx, status=202, body=body, headers=headers)
    await session.commit()
    return JSONResponse(status_code=202, content=body, headers=headers)


@router.get("/batches/{batch_id}", response_model=BatchStatus)
async def get_batch_status(
    batch_id: str = Path(..., pattern=r"^batch_[A-Za-z0-9]{16,32}$"),
    auth: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> BatchStatus:
    stmt = select(BatchRecord).where(BatchRecord.batch_id == batch_id)
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None or record.institution_id != auth.institution_id:
        raise ResourceNotFound(detail=f"batch_id {batch_id!r} not found.")
    return BatchStatus(
        batch_id=record.batch_id,
        institution_id=record.institution_id,
        status=record.status,  # type: ignore[arg-type]
        submitted_at=record.submitted_at,
        completed_at=record.completed_at,
        row_count_submitted=record.row_count_submitted,
        row_count_accepted=record.row_count_accepted,
        row_count_rejected=record.row_count_rejected,
    )


@router.get("/batches/{batch_id}/results", response_model=BatchResultsResponse)
async def get_batch_results(
    batch_id: str = Path(..., pattern=r"^batch_[A-Za-z0-9]{16,32}$"),
    page_size: int = Query(200, ge=1, le=1000),
    next_cursor: str | None = Query(None),
    auth: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> BatchResultsResponse:
    stmt = select(BatchRecord).where(BatchRecord.batch_id == batch_id)
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None or record.institution_id != auth.institution_id:
        raise ResourceNotFound(detail=f"batch_id {batch_id!r} not found.")
    # Per-row results land in Prompt 8 alongside the upload pipeline. Today
    # the endpoint returns an empty page rather than 501 so smoke and
    # conformance tests can hit it.
    return BatchResultsResponse(batch_id=batch_id, rows=[], next_cursor=None)
