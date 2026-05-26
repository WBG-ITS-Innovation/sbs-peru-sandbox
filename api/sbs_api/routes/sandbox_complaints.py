"""External-institution sandbox endpoint for granular Anexo-1A complaints.

P11A.5a — institution-to-SBS sandbox API connection.

``POST /v1/sandbox/complaints/granular`` is the external-facing
companion of the internal ``POST /v1/internal/demo/simulate-submission``
endpoint. It accepts the same PII-bearing Anexo-1A-shaped payload, but
runs the full institutional security chain that ``/v1/complaints``
uses (mTLS subject → OAuth client_credentials token with
``complaints:write`` scope → HMAC SHA-256 canonical-request signature
→ Idempotency-Key). The redaction, data-quality, audit, agent_run, and
SSE side-effects are delegated to the P11A orchestrator so behaviour
stays bit-for-bit identical between the internal demo path and the
external sandbox path.

The endpoint is sandbox infrastructure — the institution data is
synthetic, but the wire-level connection, auth, redaction, DQ, audit,
and SSE behaviour is real. It does not replace SUCAVE statistical
reporting and does not represent the production SBS production
infrastructure.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.auth.scopes import COMPLAINTS_WRITE
from sbs_api.data_quality import POLICY_VERSION as DQ_POLICY_VERSION
from sbs_api.db.session import get_sessionmaker
from sbs_api.demo_ingestion import run_demo_ingestion
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
    IdempotencyKeyInFlight,
    ResourceNotFound,
)
from sbs_api.models.demo_ingestion import (
    DataQualityEnvelope,
    DemoSubmissionRequest,
    TimelineEvent,
)
from sbs_api.redaction import POLICY_VERSION as REDACTION_POLICY_VERSION

router = APIRouter(tags=["Sandbox (Institution)"])


# ---------------------------------------------------------------------------
# Response envelope — sandbox institution receipt.
# ---------------------------------------------------------------------------


SandboxStatus = Literal[
    "accepted",
    "accepted_with_warnings",
    "rejected",
    "duplicate",
]


class SandboxGranularReceipt(BaseModel):
    """Institution-facing receipt for a sandbox granular submission.

    Carries everything an institution SDK author needs to correlate
    the submission with their own records: SBS submission id, the
    canonical complaint id, the raw-store id, the idempotency key
    that was honoured, the timeline, and the data-quality / redaction
    policy versions that were applied.
    """

    model_config = ConfigDict(extra="forbid")

    submission_id: str
    institution_id: str
    complaint_id: str
    raw_complaint_id: str
    status: SandboxStatus
    idempotency_key: str
    received_at: str
    timeline: list[TimelineEvent]
    data_quality: DataQualityEnvelope
    redaction_policy_version: str
    data_quality_policy_version: str
    event_id: int | None = None


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post(
    "/sandbox/complaints/granular",
    status_code=201,
    response_model=SandboxGranularReceipt,
    summary="Sandbox institution-facing granular complaint ingestion",
)
async def submit_granular_complaint(
    request: Request,
    body: DemoSubmissionRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    token: VerifiedToken = Depends(verified_oauth_token_with_scope(COMPLAINTS_WRITE)),
    _hmac: MtlsSubject = Depends(verified_hmac_signature),
    _rate_limit: MtlsSubject = Depends(business_bucket),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """Accept one Anexo-1A-shaped complaint over the sandbox institutional path.

    Reuses the P11A ingestion orchestrator end-to-end. Returns a 201
    with an institution receipt on success, a 200 replay (with
    ``Idempotency-Replayed: true``) on a duplicate Idempotency-Key,
    and a 409 ``IDEMPOTENCY_KEY_IN_FLIGHT`` while a concurrent request
    for the same key is still being processed.
    """

    # Tenant binding: the body's institution_id must match the
    # authenticated caller (same rule as POST /v1/complaints).
    if body.institution_id != token.institution_id:
        raise ResourceNotFound(
            detail="institution_id in body does not match the authenticated caller."
        )

    # Idempotency claim — use the raw body bytes so equivalent JSON
    # serialisations hash to the same value.
    raw_body = await request.body()
    ctx = get_idempotency_context(
        institution_id=token.institution_id,
        key=idempotency_key,
        body=raw_body,
        method=request.method,
        path=request.url.path,
    )
    claim = await claim_idempotency_slot(get_sessionmaker(), ctx)
    if claim.state == "in_flight":
        raise IdempotencyKeyInFlight(
            detail=(
                "Another request with this Idempotency-Key is still "
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

    outcome = await run_demo_ingestion(session, request=body)

    dq_report: dict[str, Any] = outcome.data_quality
    annex_1a_report: dict[str, Any] = outcome.annex_1a_data_quality or {}
    annex_results = annex_1a_report.get("results", [])
    annex_errors = [r for r in annex_results if r.get("severity") == "error"]
    annex_warnings = [r for r in annex_results if r.get("severity") == "warning"]

    has_errors = bool(dq_report.get("errors")) or bool(annex_errors)
    has_warnings = bool(dq_report.get("warnings")) or bool(annex_warnings)
    if has_errors:
        status_code = "rejected"
    elif has_warnings:
        status_code = "accepted_with_warnings"
    else:
        status_code = "accepted"

    received_at_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    receipt = {
        "submission_id": outcome.agent_run_id,
        "institution_id": outcome.institution_id,
        "complaint_id": outcome.complaint_id,
        "raw_complaint_id": outcome.raw_complaint_id,
        "status": status_code,
        "idempotency_key": idempotency_key,
        "received_at": received_at_iso,
        "timeline": outcome.timeline,
        "data_quality": dq_report,
        "annex_1a_data_quality": annex_1a_report,
        "redaction_policy_version": REDACTION_POLICY_VERSION,
        "data_quality_policy_version": DQ_POLICY_VERSION,
        "event_id": outcome.event_id,
    }

    headers = {"Location": f"/v1/complaints/{outcome.complaint_id}"}

    await mark_complete(session, ctx, status=201, body=receipt, headers=headers)
    await session.commit()

    return JSONResponse(status_code=201, content=receipt, headers=headers)
