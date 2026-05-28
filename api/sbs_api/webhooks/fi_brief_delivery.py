"""Deliver an approved FIBrief to the FI's conduct-officer endpoint.

Reuses the EXISTING signed-webhook infrastructure:
* endpoint = ``InstitutionWebhookConfig.callback_url`` (the demo FIs'
  conduct-officer endpoint points at the compose ``webhook-listener``)
* HMAC secret = ``OutboundWebhookSecret.active_secret``
* signing = :mod:`sbs_api.webhook.signing` (same canonical request +
  ``X-SBS-Signature`` / ``X-SBS-Timestamp`` / ``X-SBS-Key-Id`` headers)

Retry policy here is the P-RESHAPE-4 spec's 3 attempts with exponential
backoff (vs the batch path's 6). The HTTP send is injectable
(``sender``) so the retry behaviour is testable without a live
receiver and without monkeypatching a runtime transport — the default
sender uses a real ``httpx.AsyncClient``.

Status transitions on the FIBrief row:
    APPROVED → PENDING → SENT → DELIVERED   (2xx)
                       ↘ DELIVERY_FAILED     (all attempts fail)
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

from sbs_api.db.models.fi_brief import FIBrief
from sbs_api.db.models.fi_brief_audit import FIBriefAudit
from sbs_api.db.models.institution_webhook_config import InstitutionWebhookConfig
from sbs_api.db.models.outbound_webhook_secret import OutboundWebhookSecret
from sbs_api.webhook.signing import (
    KID_SANDBOX_V1,
    build_outbound_canonical_request,
    compute_outbound_signature,
    signature_header,
)

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
# Exponential backoff between attempts (seconds). Real workers sleep
# these; the unit test passes a no-op sleeper.
_BACKOFF_SECONDS = (2, 4)

# An injectable async HTTP sender. Returns (status_code, body_text).
Sender = Callable[[httpx.Request], Awaitable[tuple[int, str]]]


@dataclass(frozen=True)
class DeliveryOutcome:
    brief_id: str
    status: str
    attempts: int


async def _default_sender(request: httpx.Request) -> tuple[int, str]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.send(request)
        return resp.status_code, resp.text


def build_fi_brief_payload(brief: FIBrief, *, response_url: str) -> dict[str, Any]:
    """Structured JSON payload sent to the FI. IDs + structured fields
    only — peer-anonymous narrative, fixed remediation codes."""
    return {
        "event": "fi.feedback.brief",
        "brief_id": brief.brief_id,
        "institution_id": brief.institution_id,
        "motivo_code": brief.motivo_code,
        "pattern_summary_es": brief.pattern_summary_es,
        "pattern_summary_en": brief.pattern_summary_en,
        "peer_context_es": brief.peer_context_es,
        "peer_context_en": brief.peer_context_en,
        "suggested_remediation_areas": list(brief.suggested_remediation_areas),
        "response_deadline": brief.response_deadline.astimezone(
            timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evidence_complaint_count": brief.evidence_complaint_count,
        "evidence_window_start": brief.evidence_window_start.astimezone(
            timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evidence_window_end": brief.evidence_window_end.astimezone(
            timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "response_url": response_url,
    }


def _signed_request(
    *,
    callback_url: str,
    payload_json: str,
    institution_id: str,
    secret: bytes,
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
    }
    return httpx.Request("POST", callback_url, content=body, headers=headers)


async def deliver_fi_brief(
    session: AsyncSession,
    *,
    brief_id: str,
    response_url_base: str = "https://api-sandbox.sbs.gob.pe/v1/internal/fi_brief",
    sender: Sender | None = None,
    sleeper: Callable[[float], Awaitable[None]] | None = None,
) -> DeliveryOutcome:
    """Deliver an APPROVED brief. Idempotent-ish: only APPROVED briefs
    are delivered; calling on a non-APPROVED brief is a no-op that
    returns the current status.

    Retries up to :data:`MAX_ATTEMPTS` with exponential backoff. On
    success → DELIVERED. On exhaustion → DELIVERY_FAILED.
    """
    sender = sender or _default_sender

    brief = (
        await session.execute(
            select(FIBrief).where(FIBrief.brief_id == brief_id)
        )
    ).scalar_one_or_none()
    if brief is None:
        raise ValueError(f"FIBrief {brief_id} not found")
    if brief.status != "APPROVED":
        log.info(
            "deliver_fi_brief no-op: brief_id=%s status=%s (not APPROVED)",
            brief_id,
            brief.status,
        )
        return DeliveryOutcome(brief_id, brief.status, brief.delivery_attempts)

    config = (
        await session.execute(
            select(InstitutionWebhookConfig).where(
                InstitutionWebhookConfig.institution_id == brief.institution_id
            )
        )
    ).scalar_one_or_none()
    secret_row = (
        await session.execute(
            select(OutboundWebhookSecret).where(
                OutboundWebhookSecret.institution_id == brief.institution_id
            )
        )
    ).scalar_one_or_none()

    if config is None or not config.enabled or secret_row is None:
        brief.status = "DELIVERY_FAILED"
        session.add(
            FIBriefAudit(
                brief_id=brief_id,
                event_type="delivery_failed",
                event_payload={"reason": "no_config_or_secret"},
                actor="system",
            )
        )
        await session.flush()
        return DeliveryOutcome(brief_id, "DELIVERY_FAILED", brief.delivery_attempts)

    response_url = f"{response_url_base}/{brief_id}/ack"
    payload_json = json.dumps(
        build_fi_brief_payload(brief, response_url=response_url),
        separators=(",", ":"),
    )

    brief.status = "PENDING"
    brief.sent_at = datetime.now(tz=timezone.utc)
    await session.flush()

    attempts = 0
    last_error: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempts = attempt
        request = _signed_request(
            callback_url=config.callback_url,
            payload_json=payload_json,
            institution_id=brief.institution_id,
            secret=bytes(secret_row.active_secret),
        )
        try:
            status_code, _body = await sender(request)
        except Exception as exc:  # noqa: BLE001
            status_code, _body = 0, ""
            last_error = f"{type(exc).__name__}: {exc}"

        session.add(
            FIBriefAudit(
                brief_id=brief_id,
                event_type="delivery_attempt",
                event_payload={
                    "attempt": attempt,
                    "http_status": status_code,
                    "error": last_error,
                },
                actor="system",
            )
        )

        if 200 <= status_code < 300:
            brief.status = "DELIVERED"
            brief.delivered_at = datetime.now(tz=timezone.utc)
            brief.delivery_attempts = attempts
            session.add(
                FIBriefAudit(
                    brief_id=brief_id,
                    event_type="delivered",
                    event_payload={"attempt": attempt},
                    actor="system",
                )
            )
            await session.flush()
            log.info("FIBrief delivered brief_id=%s attempts=%s", brief_id, attempts)
            return DeliveryOutcome(brief_id, "DELIVERED", attempts)

        last_error = last_error or f"http_status={status_code}"
        if attempt < MAX_ATTEMPTS:
            brief.status = "SENT"  # in-flight, awaiting retry
            delay = _BACKOFF_SECONDS[min(attempt - 1, len(_BACKOFF_SECONDS) - 1)]
            if sleeper is not None:
                await sleeper(delay)

    brief.status = "DELIVERY_FAILED"
    brief.delivery_attempts = attempts
    session.add(
        FIBriefAudit(
            brief_id=brief_id,
            event_type="delivery_failed",
            event_payload={"attempts": attempts, "last_error": last_error},
            actor="system",
        )
    )
    await session.flush()
    log.error(
        "FIBrief delivery exhausted brief_id=%s attempts=%s error=%s",
        brief_id,
        attempts,
        last_error,
    )
    return DeliveryOutcome(brief_id, "DELIVERY_FAILED", attempts)
