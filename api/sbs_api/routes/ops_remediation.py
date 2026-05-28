"""SBS IT remediation actions (P-RESHAPE-9).

High-privilege operations for Rosa, gated on ``ops:remediate`` (SBS IT
only). Each carries a rationale and lands an ``incident_annotations``
audit row:

* POST /v1/internal/ops/webhooks/{delivery_id}/retry — re-arm a failed
  outbound webhook (status delivery_failed → pending, attempts += 1).
* POST /v1/internal/ops/runs/{run_id}/requeue — re-enqueue a failed agent
  run as a fresh in-progress row with the same input.
* POST /v1/internal/ops/circuit_breaker/{institution_code} — PAUSE / RESUME
  ingestion for one FI (50-char rationale).

Ops-only: no business field appears in any request or response.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.auth.persona_scopes import OPS_REMEDIATE
from sbs_api.db.models.agent_run import AgentRun
from sbs_api.db.models.fi_circuit_breaker import FiCircuitBreaker
from sbs_api.db.models.incident_annotation import IncidentAnnotation
from sbs_api.db.models.webhook_delivery import WebhookDelivery
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.persona import requires_scope
from sbs_api.routes._internal_auth import verify_internal_secret

router = APIRouter(prefix="/internal/ops", tags=["Ops"])

_REMEDIATE = requires_scope(OPS_REMEDIATE)


def _annotation(actor: str, component: str, note: str, severity: str | None = None):
    return IncidentAnnotation(
        actor_user_id=actor,
        component=component,
        severity=severity,
        note=note,
    )


class RemediationRequest(BaseModel):
    actor_user_id: str = Field(min_length=1, max_length=128)
    rationale: str = Field(min_length=20, max_length=2_000)


@router.post(
    "/webhooks/{delivery_id}/retry",
    status_code=200,
    dependencies=[Depends(verify_internal_secret)],
)
async def retry_webhook(
    delivery_id: str,
    body: RemediationRequest,
    roles: frozenset[str] = Depends(_REMEDIATE),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = (
        await session.execute(
            select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Delivery not found")
    if row.status != "delivery_failed":
        raise HTTPException(
            status_code=409,
            detail=f"delivery is {row.status}, only delivery_failed can be retried",
        )
    # Re-arm: the existing retry worker picks up pending rows.
    row.status = "pending"
    row.attempts = row.attempts + 1
    row.next_attempt_at = datetime.now(tz=timezone.utc)
    session.add(
        _annotation(
            body.actor_user_id,
            "webhook_delivery",
            f"RETRY_WEBHOOK {delivery_id}: {body.rationale}",
        )
    )
    await session.commit()
    return {"delivery_id": delivery_id, "status": "pending", "attempts": row.attempts}


@router.post(
    "/runs/{run_id}/requeue",
    status_code=201,
    dependencies=[Depends(verify_internal_secret)],
)
async def requeue_agent_run(
    run_id: str,
    body: RemediationRequest,
    roles: frozenset[str] = Depends(_REMEDIATE),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = (
        await session.execute(
            select(AgentRun).where(AgentRun.id == run_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if row.status != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"run is {row.status}, only failed runs can be requeued",
        )
    new_id = str(uuid.uuid4())
    session.add(
        AgentRun(
            id=new_id,
            complaint_id=row.complaint_id,
            agent_name=row.agent_name,
            agent_version=row.agent_version,
            started_at=datetime.now(tz=timezone.utc),
            ended_at=None,
            status="in_progress",
            tool_calls=[],
            final_output=None,
            error=None,
        )
    )
    session.add(
        _annotation(
            body.actor_user_id,
            "agent_runtime",
            f"REQUEUE_AGENT_RUN {run_id} -> {new_id}: {body.rationale}",
        )
    )
    await session.commit()
    return {"requeued_from": run_id, "new_run_id": new_id, "status": "in_progress"}


class CircuitBreakerRequest(BaseModel):
    actor_user_id: str = Field(min_length=1, max_length=128)
    action: Literal["PAUSE", "RESUME"]
    rationale: str = Field(
        min_length=50,
        max_length=2_000,
        description="Why ingestion is paused/resumed — >= 50 chars (high-privilege).",
    )


@router.post(
    "/circuit_breaker/{institution_code}",
    status_code=200,
    dependencies=[Depends(verify_internal_secret)],
)
async def set_circuit_breaker(
    institution_code: str,
    body: CircuitBreakerRequest,
    roles: frozenset[str] = Depends(_REMEDIATE),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    state = "PAUSED" if body.action == "PAUSE" else "NORMAL"
    now = datetime.now(tz=timezone.utc)
    row = (
        await session.execute(
            select(FiCircuitBreaker).where(
                FiCircuitBreaker.institution_code == institution_code
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = FiCircuitBreaker(
            institution_code=institution_code,
            state=state,
            set_by_user_id=body.actor_user_id,
            set_at=now,
            rationale=body.rationale,
        )
        session.add(row)
    else:
        row.state = state
        row.set_by_user_id = body.actor_user_id
        row.set_at = now
        row.rationale = body.rationale
    session.add(
        _annotation(
            body.actor_user_id,
            "ingestion",
            f"CIRCUIT_BREAKER {body.action} {institution_code}: {body.rationale}",
            severity="RED" if state == "PAUSED" else "GREEN",
        )
    )
    await session.commit()
    return {"institution_code": institution_code, "state": state}
