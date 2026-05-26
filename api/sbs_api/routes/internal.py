"""Server-to-server endpoints for the supervisor UI.

The Next.js supervisor UI calls FastAPI for cross-screen state that
must live on the regulator side: the audit chain. These routes are
deliberately not part of the institutional `/v1/*` surface — they sit
under `/v1/internal/*` and are authenticated by a shared secret in the
Authorization header, not by the mTLS + OAuth chain that gates
institutional requests.

The shared secret model is the minimum that lets two server processes
talk to each other under a single trust domain. Part 9 production work
hardens this with a per-route service-account JWT signed by Keycloak;
the route shape stays the same.

P11A overlay: ``POST /internal/demo/simulate-submission`` is a
sandbox-only ingestion endpoint backing the LiveIngestionPanel. It
accepts PII-bearing Anexo-1A-shaped payloads, redacts them, runs
deterministic data-quality checks, persists a canonical complaint
with the redacted text, writes one ``agent_runs`` row, records five
audit-chain events, and publishes one ``complaint.received`` SSE
delta. See ADR 0044 (redaction) and ADR 0045 (data quality).
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.audit import record_audit_event
from sbs_api.demo_ingestion import run_demo_ingestion
from sbs_api.dependencies.db import get_session
from sbs_api.models.demo_ingestion import (
    DemoSubmissionRequest,
    DemoSubmissionResponse,
)
from sbs_api.routes._internal_auth import verify_internal_secret

router = APIRouter(prefix="/internal", tags=["Internal"])


class AuditWriteRequest(BaseModel):
    """Shape the Next.js audit bridge sends. Mirrors the helper signature
    of ``sbs_api.audit.record_audit_event`` so the contract is the same
    on both sides of the wire.
    """

    actor_type: Literal["user", "agent"]
    actor_id: str = Field(min_length=1, max_length=128)
    action: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9-]*[a-z0-9]$",
        description="kebab-case action code.",
    )
    object_type: str = Field(min_length=1, max_length=32)
    object_id: str = Field(min_length=1, max_length=64)
    diff: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


class AuditWriteResponse(BaseModel):
    id: int
    created_at: str


@router.post(
    "/audit",
    response_model=AuditWriteResponse,
    status_code=201,
    dependencies=[Depends(verify_internal_secret)],
)
async def write_audit(
    body: AuditWriteRequest,
    session: AsyncSession = Depends(get_session),
) -> AuditWriteResponse:
    """Write one audit_events row on behalf of the supervisor UI.

    The supervisor UI does not own the database; this endpoint is the
    only path by which a non-FastAPI process writes to ``audit_events``.
    The Pydantic model validates the kebab-case action shape before the
    DB check constraint sees it, so a typo surfaces as a 422, not a
    500.
    """

    try:
        event = await record_audit_event(
            session,
            actor_type=body.actor_type,
            actor_id=body.actor_id,
            action=body.action,
            object_type=body.object_type,
            object_id=body.object_id,
            diff=body.diff,
            meta=body.meta,
        )
        await session.commit()
    except IntegrityError as exc:
        # Most likely cause: the DB check constraint rejected the action
        # string even though it passed Pydantic validation — should not
        # happen, but if it does we surface the constraint name.
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(exc.orig)) from exc

    return AuditWriteResponse(
        id=event.id,
        created_at=event.created_at.isoformat(timespec="seconds"),
    )


@router.post(
    "/demo/simulate-submission",
    response_model=DemoSubmissionResponse,
    status_code=201,
    dependencies=[Depends(verify_internal_secret)],
)
async def simulate_submission(
    body: DemoSubmissionRequest,
    session: AsyncSession = Depends(get_session),
) -> DemoSubmissionResponse:
    """P11A demo / sandbox ingestion endpoint.

    Accepts a realistic Anexo-1A-shaped complaint with PII fields,
    runs deterministic redaction + data-quality checks, persists the
    canonical complaint with redacted text, writes one ``agent_runs``
    row + the five audit-chain events, and publishes one SSE
    ``complaint.received`` delta. The full response carries
    everything the LiveIngestionPanel renders.

    This endpoint is **not** the production institutional path —
    ``POST /v1/complaints`` remains the production-shaped Tier 1
    surface with mTLS + OAuth + HMAC. The demo endpoint exists so
    the LiveIngestionPanel can drive a real backend without touching
    the production-like auth chain.
    """

    try:
        outcome = await run_demo_ingestion(session, request=body)
        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return DemoSubmissionResponse(
        complaint_id=outcome.complaint_id,
        raw_complaint_id=outcome.raw_complaint_id,
        institution_id=outcome.institution_id,
        institution_name=outcome.institution_name,
        agent_run_id=outcome.agent_run_id,
        event_id=outcome.event_id,
        timeline=outcome.timeline,  # type: ignore[arg-type]
        redaction_diff=outcome.redaction_diff,  # type: ignore[arg-type]
        data_quality=outcome.data_quality,  # type: ignore[arg-type]
    )
