"""Tier 2 batch ingestion endpoints (ADR 0034).

`POST /v1/batches` — accept a multipart upload (manifest JSON + CSV file),
persist the CSV, INSERT a `batches` row in state ``pending``, enqueue a
``process_batch`` job for the arq worker, and return 202 with a
``Location`` header pointing at the status endpoint.

`GET /v1/batches/{batch_id}` and `/rejections` are status endpoints; the
full rewrite for ADR 0034 lands in Workstream C. The interim
implementation in this file returns the 4-state vocabulary so Workstream
A's smoke test can assert state transitions, but uses the existing
``BatchResultsResponse``/``rejections`` semantics until C lands.

The endpoint chain is mTLS → OAuth scope ``batch:upload`` → HMAC →
business-bucket rate limit. The HMAC dep is multipart-aware (ADR 0027
amendment): the canonical-request body-hash is computed over the file
bytes only, not the multipart envelope.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

import uuid_utils as uuid7
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Path as PathParam,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.auth.cursor import (
    decode_cursor,
    encode_cursor,
    load_or_create_cursor_signing_key,
)
from sbs_api.auth.scopes import BATCH_UPLOAD
from sbs_api.config import get_settings
from sbs_api.db.models.batch import BatchRecord
from sbs_api.db.models.batch_row_rejection import BatchRowRejection
from sbs_api.db.session import get_sessionmaker
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.hmac_verify import verified_hmac_signature
from sbs_api.dependencies.idempotency import (
    claim_idempotency_slot,
    get_idempotency_context,
    mark_complete,
)
from sbs_api.dependencies.mtls import MtlsSubject
from sbs_api.dependencies.oauth import (
    VerifiedToken,
    verified_oauth_token_with_scope,
)
from sbs_api.dependencies.rate_limit import business_bucket
from sbs_api.errors.exceptions import (
    BatchChecksumMismatch,
    BatchManifestInvalid,
    CursorInvalid,
    IdempotencyKeyInFlight,
    ResourceNotFound,
)
from sbs_api.models.requests import BatchManifest
from sbs_api.models.responses import (
    BatchRejectionsResponse,
    BatchRowRejectionDetail,
    BatchStatus,
    BatchSubmission,
)
from sbs_api.observability.logging import get_logger

router = APIRouter(tags=["Ingestion (Tier 2)"])

_logger = get_logger(__name__)
_BATCH_ID_PREFIX = "batch_"


def _new_batch_id() -> str:
    # UUID v7 hex + 4 random hex chars for additional entropy. 32 chars after prefix.
    base = str(uuid7.uuid7()).replace("-", "")
    return f"{_BATCH_ID_PREFIX}{base[:24]}{secrets.token_hex(2)}"


def _resolve_storage_dir() -> Path:
    settings = get_settings()
    path = Path(settings.batch_storage_path)
    if not path.is_absolute():
        # Resolve relative to the repo root, not the working directory of
        # whoever ran the process — the path is repo-relative by spec.
        path = Path(__file__).resolve().parents[3] / settings.batch_storage_path
    path.mkdir(parents=True, exist_ok=True)
    return path


@router.post("/batches", status_code=202, response_model=BatchSubmission)
async def create_batch(
    request: Request,
    manifest: str = Form(
        ...,
        description="JSON-encoded manifest (BatchManifest schema).",
    ),
    file: UploadFile = File(
        ...,
        description="CSV file containing Anexo 1-A rows.",
    ),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    token: VerifiedToken = Depends(
        verified_oauth_token_with_scope(BATCH_UPLOAD)
    ),
    _hmac: MtlsSubject = Depends(verified_hmac_signature),
    _rate_limit: MtlsSubject = Depends(business_bucket),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    # --- 1. Parse + validate manifest -----------------------------------
    try:
        manifest_dict = json.loads(manifest)
    except json.JSONDecodeError as exc:
        raise BatchManifestInvalid(
            detail=f"Manifest is not valid JSON: {exc.msg}."
        ) from exc

    try:
        manifest_obj = BatchManifest.model_validate(manifest_dict)
    except ValidationError as exc:
        # Surface the first error in `detail`; full errors envelope is
        # logged for support.
        first = exc.errors()[0]
        loc = ".".join(str(p) for p in first["loc"])
        raise BatchManifestInvalid(
            detail=f"Manifest field {loc!r}: {first['msg']}."
        ) from exc

    # --- 2. Read the file (already buffered by the size middleware) -----
    await file.seek(0)
    csv_bytes = await file.read()
    actual_sha256 = hashlib.sha256(csv_bytes).hexdigest()
    if actual_sha256 != manifest_obj.checksum_sha256:
        raise BatchChecksumMismatch(
            detail=(
                f"Manifest checksum {manifest_obj.checksum_sha256!r} does "
                f"not match the SHA-256 of the received CSV "
                f"({actual_sha256!r}). Recompute and resubmit."
            )
        )

    # --- 3. Idempotency claim -------------------------------------------
    # Hash basis: the manifest bytes plus the CSV checksum (already
    # verified to match the file). This is a stable, deterministic
    # representation of the logical request that avoids re-reading the
    # multipart envelope (which Starlette will not re-yield once the
    # form parser has consumed it).
    idem_body = manifest.encode("utf-8") + b"\n" + manifest_obj.checksum_sha256.encode("ascii")
    ctx = get_idempotency_context(
        institution_id=token.institution_id,
        key=idempotency_key,
        body=idem_body,
        method=request.method,
        path=request.url.path,
    )
    claim = await claim_idempotency_slot(get_sessionmaker(), ctx)
    if claim.state == "in_flight":
        raise IdempotencyKeyInFlight(
            detail=(
                "Another batch upload with this Idempotency-Key is still "
                "processing. Retry in a moment."
            ),
            extra_headers={"Retry-After": "1"},
        )
    if claim.state == "replay":
        assert claim.record is not None
        cached_body = json.loads(claim.record.response_payload)
        cached_headers = json.loads(claim.record.response_headers)
        cached_headers["Idempotency-Replayed"] = "true"
        return JSONResponse(
            status_code=claim.record.response_status,
            content=cached_body,
            headers=cached_headers,
        )

    # --- 4. Persist CSV to disk -----------------------------------------
    batch_id = _new_batch_id()
    storage_dir = _resolve_storage_dir()
    file_name = file.filename or f"{batch_id}.csv"
    on_disk_path = storage_dir / f"{batch_id}.csv"
    on_disk_path.write_bytes(csv_bytes)
    settings = get_settings()
    # Store the basename only. The worker resolves the full path via
    # settings.batch_storage_path so the API host and the worker
    # container can mount the same data directory at different paths.
    rel_file_name = f"{batch_id}.csv"

    # --- 5. INSERT batch row --------------------------------------------
    record = BatchRecord(
        batch_id=batch_id,
        institution_id=token.institution_id,
        file_name=file_name,
        reporting_period_start=manifest_obj.reporting_period_start,
        reporting_period_end=manifest_obj.reporting_period_end,
        schema_version=manifest_obj.schema_version or settings.schema_version,
        row_count_submitted=manifest_obj.row_count_submitted,
        sha256=manifest_obj.checksum_sha256,
        status="pending",
        file_path=rel_file_name,
    )
    session.add(record)
    await session.flush()

    # --- 6. Enqueue arq job ---------------------------------------------
    # The job picks up the batch_id and reads the file from disk. On
    # arq pool errors (Redis unreachable, etc.) we log and continue —
    # the batch row is durable, and an operator can re-enqueue. The
    # status endpoint surfaces `pending` indefinitely in that case.
    try:
        from sbs_api.workers.arq_pool import enqueue_job

        await enqueue_job("process_batch", batch_id)
        _logger.info(
            "batch.enqueue.success",
            batch_id=batch_id,
            institution_id=token.institution_id,
            row_count_submitted=manifest_obj.row_count_submitted,
        )
    except Exception:  # noqa: BLE001
        _logger.error(
            "batch.enqueue.failed",
            batch_id=batch_id,
            institution_id=token.institution_id,
            exc_info=True,
        )

    # --- 7. Compose response --------------------------------------------
    submission = BatchSubmission(batch_id=batch_id, status="pending")
    body = submission.model_dump(mode="json")
    location = f"/v1/batches/{batch_id}"
    headers: dict[str, str] = {"Location": location}
    await mark_complete(session, ctx, status=202, body=body, headers=headers)
    await session.commit()
    return JSONResponse(status_code=202, content=body, headers=headers)


@router.get("/batches/{batch_id}", response_model=BatchStatus)
async def get_batch_status(
    batch_id: str = PathParam(..., pattern=r"^batch_[A-Za-z0-9]{16,32}$"),
    token: VerifiedToken = Depends(
        verified_oauth_token_with_scope(BATCH_UPLOAD)
    ),
    _rate_limit: MtlsSubject = Depends(business_bucket),
    session: AsyncSession = Depends(get_session),
) -> BatchStatus:
    stmt = select(BatchRecord).where(BatchRecord.batch_id == batch_id)
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None or record.institution_id != token.institution_id:
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
        failure_reason=record.failure_reason,
    )


_cursor_signing_key: bytes | None = None


def _get_cursor_signing_key() -> bytes:
    global _cursor_signing_key
    if _cursor_signing_key is None:
        _cursor_signing_key = load_or_create_cursor_signing_key()
    return _cursor_signing_key


def override_cursor_signing_key_for_test(key: bytes) -> None:
    global _cursor_signing_key
    _cursor_signing_key = key


def reset_cursor_signing_key_for_test() -> None:
    global _cursor_signing_key
    _cursor_signing_key = None


def _encode_rejection_cursor(last_id: int) -> str:
    return encode_cursor({"id": last_id}, key=_get_cursor_signing_key())


def _decode_rejection_cursor(cursor: str) -> int:
    try:
        payload = decode_cursor(cursor, key=_get_cursor_signing_key())
        return int(payload["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise CursorInvalid(
            detail=(
                "Cursor value could not be decoded or its signature is "
                "invalid. Pass back the value the server returned verbatim; "
                "do not modify it."
            )
        ) from exc


@router.get(
    "/batches/{batch_id}/rejections",
    response_model=BatchRejectionsResponse,
)
async def get_batch_rejections(
    batch_id: str = PathParam(..., pattern=r"^batch_[A-Za-z0-9]{16,32}$"),
    page_size: int = Query(200, ge=1, le=1000),
    next_cursor: str | None = Query(None),
    token: VerifiedToken = Depends(
        verified_oauth_token_with_scope(BATCH_UPLOAD)
    ),
    _rate_limit: MtlsSubject = Depends(business_bucket),
    session: AsyncSession = Depends(get_session),
) -> BatchRejectionsResponse:
    stmt = select(BatchRecord).where(BatchRecord.batch_id == batch_id)
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None or record.institution_id != token.institution_id:
        raise ResourceNotFound(detail=f"batch_id {batch_id!r} not found.")

    rej_stmt = select(BatchRowRejection).where(
        BatchRowRejection.batch_id == batch_id
    )
    if next_cursor is not None:
        cursor_id = _decode_rejection_cursor(next_cursor)
        rej_stmt = rej_stmt.where(BatchRowRejection.id > cursor_id)
    rej_stmt = rej_stmt.order_by(BatchRowRejection.id.asc()).limit(
        page_size + 1
    )

    rej_result = await session.execute(rej_stmt)
    rows = list(rej_result.scalars().all())
    has_more = len(rows) > page_size
    page = rows[:page_size]
    next_cursor_out: str | None = None
    if has_more and page:
        next_cursor_out = _encode_rejection_cursor(page[-1].id)

    return BatchRejectionsResponse(
        batch_id=batch_id,
        rejections=[
            BatchRowRejectionDetail(
                row_index=r.row_index,
                field=r.field,
                rule=r.rule,
                message=r.message,
            )
            for r in page
        ],
        next_cursor=next_cursor_out,
    )
