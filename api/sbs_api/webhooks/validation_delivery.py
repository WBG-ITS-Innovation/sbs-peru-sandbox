"""DIValeVale validation outbound webhooks (P-RESHAPE-8).

Two new payload types, both signed with the EXISTING HMAC chain and
both carrying ONLY ids + codes — never narrative text:

* ``VALIDATION_BATCH_REJECTION``     — Tier-2 quarantine diagnostic
* ``VALIDATION_ENRICHMENT_REQUEST``  — Tier-1 enrichment ask

The HTTP send is injectable for tests (no live receiver needed).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.institution_webhook_config import InstitutionWebhookConfig
from sbs_api.db.models.outbound_webhook_secret import OutboundWebhookSecret
from sbs_api.webhook.signing import (
    KID_SANDBOX_V1,
    build_outbound_canonical_request,
    compute_outbound_signature,
    signature_header,
)

log = logging.getLogger(__name__)

PAYLOAD_TYPE_HEADER = "X-Payload-Type"
PAYLOAD_BATCH_REJECTION = "VALIDATION_BATCH_REJECTION"
PAYLOAD_ENRICHMENT_REQUEST = "VALIDATION_ENRICHMENT_REQUEST"

Sender = Callable[[httpx.Request], Awaitable[tuple[int, str]]]


@dataclass(frozen=True)
class ValidationDeliveryOutcome:
    payload_type: str
    status: str
    attempts: int


async def _default_sender(request: httpx.Request) -> tuple[int, str]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.send(request)
        return resp.status_code, resp.text


def _signed_request(
    *,
    callback_url: str,
    payload_json: str,
    institution_id: str,
    secret: bytes,
    payload_type: str,
) -> httpx.Request:
    parsed = urlparse(callback_url)
    callback_path = parsed.path or "/"
    if parsed.query:
        callback_path = f"{callback_path}?{parsed.query}"
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = payload_json.encode("utf-8")
    canonical = build_outbound_canonical_request(
        method="POST",
        callback_path=callback_path,
        timestamp=timestamp,
        body=body,
        institution_id=institution_id,
    )
    sig = compute_outbound_signature(secret, canonical)
    headers = {
        "Content-Type": "application/json",
        "X-SBS-Timestamp": timestamp,
        "X-SBS-Signature": signature_header(sig),
        "X-SBS-Key-Id": KID_SANDBOX_V1,
        PAYLOAD_TYPE_HEADER: payload_type,
    }
    return httpx.Request("POST", callback_url, content=body, headers=headers)


async def _deliver(
    session: AsyncSession,
    *,
    sbs_institution_id: str,
    payload: dict[str, Any],
    payload_type: str,
    sender: Sender | None,
    max_attempts: int = 3,
) -> ValidationDeliveryOutcome:
    sender = sender or _default_sender
    config = (
        await session.execute(
            select(InstitutionWebhookConfig).where(
                InstitutionWebhookConfig.institution_id == sbs_institution_id
            )
        )
    ).scalar_one_or_none()
    secret_row = (
        await session.execute(
            select(OutboundWebhookSecret).where(
                OutboundWebhookSecret.institution_id == sbs_institution_id
            )
        )
    ).scalar_one_or_none()
    if config is None or not config.enabled or secret_row is None:
        return ValidationDeliveryOutcome(payload_type, "DELIVERY_FAILED", 0)

    payload_json = json.dumps(payload, separators=(",", ":"))
    attempts = 0
    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        req = _signed_request(
            callback_url=config.callback_url,
            payload_json=payload_json,
            institution_id=sbs_institution_id,
            secret=bytes(secret_row.active_secret),
            payload_type=payload_type,
        )
        try:
            status_code, _ = await sender(req)
        except Exception:  # noqa: BLE001
            status_code = 0
        if 200 <= status_code < 300:
            return ValidationDeliveryOutcome(payload_type, "DELIVERED", attempts)
    return ValidationDeliveryOutcome(payload_type, "DELIVERY_FAILED", attempts)


def build_batch_rejection_payload(
    *, batch_id: str, row_count: int, per_row_codes: list[dict[str, Any]], resubmit_url: str
) -> dict[str, Any]:
    """Codes + ids only — NO narrative echoed back."""
    return {
        "event": "validation.batch.rejection",
        "batch_id": batch_id,
        "row_count": row_count,
        "per_row_failure_codes": per_row_codes,  # [{row_ref, verdict, codes:[...]}]
        "resubmit_url": resubmit_url,
    }


def build_enrichment_request_payload(
    *, complaint_id: str, missing_fields: list[str], deadline: datetime, resubmit_url: str
) -> dict[str, Any]:
    return {
        "event": "validation.enrichment.request",
        "complaint_id": complaint_id,
        "missing_fields": missing_fields,
        "deadline": deadline.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resubmit_url": resubmit_url,
    }


async def deliver_batch_rejection(
    session: AsyncSession,
    *,
    sbs_institution_id: str,
    payload: dict[str, Any],
    sender: Sender | None = None,
) -> ValidationDeliveryOutcome:
    return await _deliver(
        session,
        sbs_institution_id=sbs_institution_id,
        payload=payload,
        payload_type=PAYLOAD_BATCH_REJECTION,
        sender=sender,
    )


async def deliver_enrichment_request(
    session: AsyncSession,
    *,
    sbs_institution_id: str,
    payload: dict[str, Any],
    sender: Sender | None = None,
) -> ValidationDeliveryOutcome:
    return await _deliver(
        session,
        sbs_institution_id=sbs_institution_id,
        payload=payload,
        payload_type=PAYLOAD_ENRICHMENT_REQUEST,
        sender=sender,
    )
