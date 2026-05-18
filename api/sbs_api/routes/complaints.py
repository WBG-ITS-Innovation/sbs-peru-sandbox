"""Tier 1 complaint endpoints.

Five endpoints from the canonical OpenAPI spec land here:

* ``POST /complaints``                          — create.
* ``GET /complaints``                           — list with cursor pagination.
* ``GET /complaints/{complaint_id}``            — retrieve.
* ``PATCH /complaints/{complaint_id}/status``   — transition resolution status.

The route handler is the enforcement point for tenant binding (the body's
``institution_id`` must match the caller's identity from
:func:`get_auth_context`). Tenant mismatch on a read returns 404, not 403,
so existence does not leak across tenants. See open-questions §5.6.
"""

from __future__ import annotations

import base64
import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.dependencies.auth import AuthContext, get_auth_context
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.etag import compute_etag
from sbs_api.dependencies.idempotency import (
    get_idempotency_context,
    lookup_cached,
    store as store_idempotency,
)
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.errors.exceptions import (
    CursorInvalid,
    ETagMismatch,
    PreconditionRequired,
    ResolutionStatusTransitionForbidden,
    ResourceNotFound,
    SBSAPIException,
)
from sbs_api.models.anexo_1a import (
    Channel,
    MotivoCode,
    ProductCategory,
    ResolutionStatus,
)
from sbs_api.models.requests import ComplaintStatusPatch, ComplaintSubmission
from sbs_api.models.responses import (
    ComplaintCreated,
    ComplaintListItem,
    ComplaintListResponse,
)
from sbs_api.state_machine.resolution_status import is_allowed

router = APIRouter(tags=["Ingestion (Tier 1)"])


# --- helpers ---------------------------------------------------------------


def _orm_to_complaint_dict(record: ComplaintRecord) -> dict:
    return {
        "complaint_id": record.complaint_id,
        "institution_id": record.institution_id,
        "received_date": record.received_date.isoformat(),
        "complainant_doc_type": record.complainant_doc_type,
        "product_category": record.product_category,
        "channel": record.channel,
        "motivo_code": record.motivo_code,
        "severity": record.severity,
        "description_text": record.description_text,
        "description_language": record.description_language,
        "complainant_age_range": record.complainant_age_range,
        "complainant_district": record.complainant_district,
        "submission_method": record.submission_method,
        "original_reference_id": record.original_reference_id,
        "resolution_status": record.resolution_status,
    }


def _orm_to_list_item(record: ComplaintRecord) -> ComplaintListItem:
    return ComplaintListItem(
        complaint_id=record.complaint_id,
        institution_id=record.institution_id,
        received_date=record.received_date,
        product_category=ProductCategory(record.product_category),
        channel=Channel(record.channel),
        motivo_code=MotivoCode(record.motivo_code),
        severity=record.severity,  # type: ignore[arg-type]
        resolution_status=ResolutionStatus(record.resolution_status),
        received_at=record.received_at,
    )


def _encode_cursor(received_at: datetime, complaint_id: str) -> str:
    payload = {"received_at": received_at.isoformat(), "complaint_id": complaint_id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(payload["received_at"]), payload["complaint_id"]
    except Exception as exc:  # noqa: BLE001 — any parse error is CURSOR_INVALID
        raise CursorInvalid(
            detail="Cursor value could not be decoded. Pass back the value the server returned verbatim."
        ) from exc


# --- POST /complaints ------------------------------------------------------


@router.post(
    "/complaints",
    status_code=201,
    response_model=ComplaintCreated,
)
async def create_complaint(
    request: Request,
    response: Response,
    submission: ComplaintSubmission,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    auth: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> Response:
    # Tenant binding: body institution_id must match the authenticated caller.
    if submission.complaint.institution_id != auth.institution_id:
        raise ResourceNotFound(
            detail="institution_id in body does not match the authenticated caller."
        )

    # Idempotency: build context from the raw body so the hash matches across
    # equivalent JSON serialisations.
    body_bytes = await request.body()
    ctx = get_idempotency_context(
        institution_id=auth.institution_id,
        key=idempotency_key,
        body=body_bytes,
        method=request.method,
        path=request.url.path,
    )
    cached = await lookup_cached(session, ctx)
    if cached is not None:
        cached_body = json.loads(cached.response_payload)
        cached_headers = json.loads(cached.response_headers)
        cached_headers["Idempotency-Replayed"] = "true"
        return JSONResponse(
            status_code=cached.response_status,
            content=cached_body,
            headers=cached_headers,
        )

    record = ComplaintRecord(
        complaint_id=submission.complaint.complaint_id,
        institution_id=submission.complaint.institution_id,
        received_date=submission.complaint.received_date,
        complainant_doc_type=submission.complaint.complainant_doc_type,
        product_category=submission.complaint.product_category,
        channel=submission.complaint.channel,
        motivo_code=submission.complaint.motivo_code,
        severity=submission.complaint.severity,
        description_text=submission.complaint.description_text,
        description_language=submission.complaint.description_language,
        complainant_age_range=submission.complaint.complainant_age_range,
        complainant_district=submission.complaint.complainant_district,
        submission_method=submission.complaint.submission_method,
        original_reference_id=submission.complaint.original_reference_id,
        resolution_status=submission.complaint.resolution_status,
        client_submission_id=submission.client_submission_id,
    )
    session.add(record)
    try:
        await session.flush()
    except IntegrityError as exc:
        # Most likely a duplicate complaint_id PK.
        raise SBSAPIException(
            detail="A complaint with this complaint_id already exists for this institution.",
        ) from exc

    received_at = record.received_at or datetime.now(timezone.utc)
    body = ComplaintCreated(
        complaint_id=record.complaint_id,
        institution_id=record.institution_id,
        received_at=received_at,
        resolution_status=ResolutionStatus(record.resolution_status),
        client_submission_id=record.client_submission_id,
    ).model_dump(mode="json")
    etag = compute_etag(record.complaint_id, record.etag_version)
    headers = {
        "Location": f"/v1/complaints/{record.complaint_id}",
        "ETag": etag,
    }

    await store_idempotency(
        session, ctx, status=201, body=body, headers=headers
    )
    await session.commit()

    for k, v in headers.items():
        response.headers[k] = v
    response.status_code = 201
    return JSONResponse(status_code=201, content=body, headers=headers)


# --- GET /complaints (list) -----------------------------------------------


@router.get("/complaints", response_model=ComplaintListResponse)
async def list_complaints(
    received_date_from: date | None = Query(None),
    received_date_to: date | None = Query(None),
    product_category: ProductCategory | None = Query(None),
    channel: Channel | None = Query(None),
    motivo_code: MotivoCode | None = Query(None),
    resolution_status: ResolutionStatus | None = Query(None),
    page_size: int = Query(50, ge=1, le=200),
    next_cursor: str | None = Query(None),
    auth: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> ComplaintListResponse:
    stmt = select(ComplaintRecord).where(
        ComplaintRecord.institution_id == auth.institution_id
    )
    if received_date_from is not None:
        stmt = stmt.where(ComplaintRecord.received_date >= received_date_from)
    if received_date_to is not None:
        stmt = stmt.where(ComplaintRecord.received_date <= received_date_to)
    if product_category is not None:
        stmt = stmt.where(ComplaintRecord.product_category == product_category.value)
    if channel is not None:
        stmt = stmt.where(ComplaintRecord.channel == channel.value)
    if motivo_code is not None:
        stmt = stmt.where(ComplaintRecord.motivo_code == motivo_code.value)
    if resolution_status is not None:
        stmt = stmt.where(ComplaintRecord.resolution_status == resolution_status.value)

    if next_cursor is not None:
        cursor_received_at, cursor_complaint_id = _decode_cursor(next_cursor)
        # Keyset pagination: (received_at, complaint_id) < cursor (DESC).
        stmt = stmt.where(
            (ComplaintRecord.received_at < cursor_received_at)
            | (
                (ComplaintRecord.received_at == cursor_received_at)
                & (ComplaintRecord.complaint_id < cursor_complaint_id)
            )
        )

    stmt = stmt.order_by(
        ComplaintRecord.received_at.desc(), ComplaintRecord.complaint_id.desc()
    ).limit(page_size + 1)

    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > page_size
    page = rows[:page_size]
    next_cursor_out: str | None = None
    if has_more and page:
        last = page[-1]
        next_cursor_out = _encode_cursor(last.received_at, last.complaint_id)

    return ComplaintListResponse(
        items=[_orm_to_list_item(r) for r in page],
        next_cursor=next_cursor_out,
    )


# --- GET /complaints/{id} -------------------------------------------------


@router.get("/complaints/{complaint_id}")
async def get_complaint(
    response: Response,
    complaint_id: str = Path(..., pattern=r"^[A-Z0-9]{1,4}-\d{4}-\d{6,10}$"),
    auth: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    stmt = select(ComplaintRecord).where(ComplaintRecord.complaint_id == complaint_id)
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None or record.institution_id != auth.institution_id:
        # Tenant mismatch and not-found both return 404 — does not leak existence.
        raise ResourceNotFound(
            detail=f"complaint_id {complaint_id!r} not found."
        )
    etag = compute_etag(record.complaint_id, record.etag_version)
    response.headers["ETag"] = etag
    return _orm_to_complaint_dict(record)


# --- PATCH /complaints/{id}/status ----------------------------------------


@router.patch("/complaints/{complaint_id}/status")
async def patch_complaint_status(
    request: Request,
    response: Response,
    patch: ComplaintStatusPatch,
    complaint_id: str = Path(..., pattern=r"^[A-Z0-9]{1,4}-\d{4}-\d{6,10}$"),
    if_match: str | None = Header(None, alias="If-Match"),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    auth: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if if_match is None:
        raise PreconditionRequired(
            detail="If-Match header required. Read the current resource and send its ETag."
        )

    stmt = select(ComplaintRecord).where(ComplaintRecord.complaint_id == complaint_id)
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()
    if record is None or record.institution_id != auth.institution_id:
        raise ResourceNotFound(detail=f"complaint_id {complaint_id!r} not found.")

    current_etag = compute_etag(record.complaint_id, record.etag_version)
    if if_match != current_etag:
        raise ETagMismatch(
            detail=(
                "The If-Match header does not match the current resource ETag. "
                "Re-fetch and resubmit with the fresh ETag."
            ),
            instance=str(request.url.path),
        )

    current_status = ResolutionStatus(record.resolution_status)
    requested = patch.resolution_status
    if not is_allowed(current_status, requested):
        raise ResolutionStatusTransitionForbidden(
            detail=(
                f"Transition {current_status.value} → {requested.value} is not "
                "permitted by the resolution_status state machine."
            )
        )

    record.resolution_status = requested.value
    record.etag_version = record.etag_version + 1
    record.updated_at = datetime.now(timezone.utc)
    await session.flush()
    await session.commit()

    response.headers["ETag"] = compute_etag(record.complaint_id, record.etag_version)
    return _orm_to_complaint_dict(record)
