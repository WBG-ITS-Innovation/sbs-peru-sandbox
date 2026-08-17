# SPDX-License-Identifier: Apache-2.0
"""Outbound webhook delivery worker job (ADR 0035).

``deliver_webhook_for_batch(ctx, batch_id, event_type)`` is the arq
entry point. The function:

1. Loads the institution's callback URL and outbound HMAC secret.
2. Validates the URL via :mod:`sbs_api.webhook.url_validation`. On
   rejection: write a ``webhook_deliveries`` row with
   ``status='delivery_failed'`` + ``failure_reason='WEBHOOK_URL_REJECTED'``,
   emit a structlog event, no retry.
3. Builds the payload (batch_id, event_type, row counts, timestamps),
   signs it with the canonical-request shape from
   :mod:`sbs_api.webhook.signing`, and POSTs via httpx.
4. On 2xx — mark ``delivered``. On 5xx / timeout / connect-failure
   schedule the next retry per ADR 0035's backoff sequence
   (30s, 2min, 10min, 1hr, 6hr).
5. On exhaustion (5 attempts) — mark ``delivery_failed`` with the
   last attempt's outcome in ``failure_reason``; emit
   ``webhook.delivery.dead_letter`` with the full attempt history.

Each attempt emits ``webhook.delivery.attempt`` with the canonical
event schema from §F.3 of the prompt spec.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from arq.worker import Retry
from sqlalchemy import select

from sbs_api.config import get_settings
from sbs_api.db.models.batch import BatchRecord
from sbs_api.db.models.institution_webhook_config import (
    InstitutionWebhookConfig,
)
from sbs_api.db.models.outbound_webhook_secret import OutboundWebhookSecret
from sbs_api.db.models.webhook_delivery import WebhookDelivery
from sbs_api.db.session import get_sessionmaker
from sbs_api.observability.logging import get_logger
from sbs_api.webhook.signing import (
    KID_SANDBOX_V1,
    build_outbound_canonical_request,
    compute_outbound_signature,
    signature_header,
)
from sbs_api.webhook.url_validation import validate_callback_url

_logger = get_logger(__name__)

# ADR 0035: Stripe-shaped backoff. Five retries after the initial
# attempt — six attempts total, ~7.7-hour window. The delays are
# pre-paired so ``_RETRY_DELAYS_SECONDS[job_try-1]`` gives the wait
# before the next attempt:
#   job_try=1 fails → wait 30s    → attempt 2
#   job_try=2 fails → wait 2min   → attempt 3
#   job_try=3 fails → wait 10min  → attempt 4
#   job_try=4 fails → wait 1hr    → attempt 5
#   job_try=5 fails → wait 6hr    → attempt 6
#   job_try=6 fails → DEAD LETTER (no further retry)
_RETRY_DELAYS_SECONDS: tuple[int, ...] = (30, 120, 600, 3600, 21600)
_MAX_ATTEMPTS = len(_RETRY_DELAYS_SECONDS) + 1  # 6 attempts total


def _new_delivery_id() -> str:
    return f"whd_{secrets.token_hex(16)}"


def _payload_for_batch(batch: BatchRecord, event_type: str) -> dict[str, Any]:
    return {
        "event": event_type,
        "batch_id": batch.batch_id,
        "institution_id": batch.institution_id,
        "status": batch.status,
        "row_count_submitted": batch.row_count_submitted,
        "row_count_accepted": batch.row_count_accepted,
        "row_count_rejected": batch.row_count_rejected,
        "completed_at": (
            batch.completed_at.isoformat()
            if batch.completed_at is not None
            else None
        ),
    }


def _iso8601_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _ensure_delivery_row(
    *,
    batch_id: str,
    institution_id: str,
    event_type: str,
    payload_json: str,
) -> str:
    sessionmaker = get_sessionmaker()
    delivery_id = _new_delivery_id()
    async with sessionmaker() as session:
        async with session.begin():
            session.add(
                WebhookDelivery(
                    delivery_id=delivery_id,
                    batch_id=batch_id,
                    institution_id=institution_id,
                    event_type=event_type,
                    payload=payload_json,
                    status="pending",
                    attempts=0,
                    attempt_history="[]",
                    next_attempt_at=datetime.now(timezone.utc),
                )
            )
    return delivery_id


async def _record_attempt(
    *,
    delivery_id: str,
    attempt_num: int,
    outcome: str,
    http_status: int | None,
    latency_ms: int | None,
    error: str | None,
    terminal_status: str | None,
    next_attempt_at: datetime | None,
    failure_reason: str | None,
) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        async with session.begin():
            stmt = select(WebhookDelivery).where(
                WebhookDelivery.delivery_id == delivery_id
            )
            row = (await session.execute(stmt)).scalar_one()
            history = json.loads(row.attempt_history)
            history.append(
                {
                    "attempt_num": attempt_num,
                    "started_at": _iso8601_utc(datetime.now(timezone.utc)),
                    "http_status": http_status,
                    "latency_ms": latency_ms,
                    "outcome": outcome,
                    "error": error,
                }
            )
            row.attempts = attempt_num
            row.attempt_history = json.dumps(history)
            row.last_attempt_at = datetime.now(timezone.utc)
            row.next_attempt_at = next_attempt_at
            if terminal_status is not None:
                row.status = terminal_status
                row.completed_at = datetime.now(timezone.utc)
                row.failure_reason = failure_reason
            else:
                row.status = "pending"
    _logger.info(
        "webhook.delivery.attempt",
        delivery_id=delivery_id,
        attempt_num=attempt_num,
        http_status=http_status,
        latency_ms=latency_ms,
        outcome=outcome,
        next_retry_at=(
            _iso8601_utc(next_attempt_at)
            if next_attempt_at is not None
            else None
        ),
    )
    if terminal_status == "delivery_failed":
        _logger.error(
            "webhook.delivery.dead_letter",
            delivery_id=delivery_id,
            attempt_count=attempt_num,
            failure_reason=failure_reason,
        )


def _post_request_for_delivery(
    *,
    callback_url: str,
    payload_json: str,
    institution_id: str,
    outbound_secret: bytes,
) -> tuple[httpx.Request, str]:
    """Build the signed httpx.Request and return it + the path used for signing."""

    parsed = urlparse(callback_url)
    callback_path = parsed.path or "/"
    if parsed.query:
        callback_path = f"{callback_path}?{parsed.query}"

    timestamp = _iso8601_utc(datetime.now(timezone.utc))
    body_bytes = payload_json.encode("utf-8")
    canonical = build_outbound_canonical_request(
        method="POST",
        callback_path=callback_path,
        timestamp=timestamp,
        body=body_bytes,
        institution_id=institution_id,
    )
    sig_b64 = compute_outbound_signature(outbound_secret, canonical)
    headers = {
        "Content-Type": "application/json",
        "X-SBS-Timestamp": timestamp,
        "X-SBS-Signature": signature_header(sig_b64),
        "X-SBS-Key-Id": KID_SANDBOX_V1,
    }
    return (
        httpx.Request("POST", callback_url, content=body_bytes, headers=headers),
        callback_path,
    )


async def deliver_webhook_for_batch(
    ctx: dict[str, Any],
    batch_id: str,
    event_type: str,
) -> dict[str, Any]:
    """Schedule and run the next delivery attempt for ``batch_id``.

    arq calls this with ``job_try`` in ctx; we map that to the attempt
    number and choose the appropriate backoff for the next attempt.
    """

    job_try = ctx.get("job_try", 1) if ctx else 1
    settings = get_settings()
    sessionmaker = get_sessionmaker()

    # On the first attempt: create the delivery row and look up the
    # institution's config + secret. Subsequent attempts replay against
    # the existing row.
    async with sessionmaker() as session:
        async with session.begin():
            batch = (
                await session.execute(
                    select(BatchRecord).where(BatchRecord.batch_id == batch_id)
                )
            ).scalar_one_or_none()
            if batch is None:
                _logger.error(
                    "webhook.delivery.batch_not_found", batch_id=batch_id
                )
                return {"batch_id": batch_id, "status": "batch_not_found"}

            config = (
                await session.execute(
                    select(InstitutionWebhookConfig).where(
                        InstitutionWebhookConfig.institution_id
                        == batch.institution_id
                    )
                )
            ).scalar_one_or_none()
            secret_row = (
                await session.execute(
                    select(OutboundWebhookSecret).where(
                        OutboundWebhookSecret.institution_id
                        == batch.institution_id
                    )
                )
            ).scalar_one_or_none()

    if config is None or not config.enabled:
        _logger.info(
            "webhook.delivery.no_config",
            batch_id=batch_id,
            institution_id=batch.institution_id,
        )
        return {"batch_id": batch_id, "status": "no_config"}
    if secret_row is None:
        _logger.error(
            "webhook.delivery.no_secret",
            batch_id=batch_id,
            institution_id=batch.institution_id,
        )
        return {"batch_id": batch_id, "status": "no_secret"}

    callback_url = config.callback_url
    payload = _payload_for_batch(batch, event_type)
    payload_json = json.dumps(payload, separators=(",", ":"))

    # Reuse an existing delivery row for retries (arq job_try>1 on the
    # same job id). For a first run, create a new row.
    existing = await _find_pending_delivery(batch_id=batch_id, event_type=event_type)
    if existing is None:
        delivery_id = await _ensure_delivery_row(
            batch_id=batch_id,
            institution_id=batch.institution_id,
            event_type=event_type,
            payload_json=payload_json,
        )
    else:
        delivery_id = existing

    # --- URL validation ---------------------------------------------
    # ADR 0035 §webhook-url-validation. The validation result carries
    # the resolved IP so a future connection-layer pin can close the
    # DNS-rebinding TOCTOU window. The pinning itself is tracked as a
    # Prompt 8 second-opinion follow-up (the sandbox dev-override
    # bypasses validation entirely, so the TOCTOU window is only a
    # concern in production-mode deployments — which Part 9 covers).
    validation = validate_callback_url(callback_url)
    if not validation.valid:
        await _record_attempt(
            delivery_id=delivery_id,
            attempt_num=job_try,
            outcome="url_rejected",
            http_status=None,
            latency_ms=None,
            error=validation.reason,
            terminal_status="delivery_failed",
            next_attempt_at=None,
            failure_reason=f"{validation.code}: {validation.reason}",
        )
        return {
            "batch_id": batch_id,
            "delivery_id": delivery_id,
            "status": "delivery_failed",
            "reason": validation.reason,
        }
    _logger.info(
        "webhook.delivery.url_validated",
        delivery_id=delivery_id,
        host_resolved_to=validation.resolved_address,
    )

    # --- Build + send -----------------------------------------------
    request, _ = _post_request_for_delivery(
        callback_url=callback_url,
        payload_json=payload_json,
        institution_id=batch.institution_id,
        outbound_secret=bytes(secret_row.active_secret),
    )

    timeout = settings.webhook_request_timeout_seconds
    started = datetime.now(timezone.utc)
    outcome: str
    http_status: int | None = None
    error: str | None = None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.send(request)
        http_status = response.status_code
        if 200 <= response.status_code < 300:
            outcome = "delivered"
        else:
            outcome = "http_error"
    except httpx.TimeoutException as exc:
        outcome = "timeout"
        error = str(exc)
    except httpx.HTTPError as exc:
        outcome = "connect_failed"
        error = f"{type(exc).__name__}: {exc}"

    latency_ms = int(
        (datetime.now(timezone.utc) - started).total_seconds() * 1000
    )

    if outcome == "delivered":
        await _record_attempt(
            delivery_id=delivery_id,
            attempt_num=job_try,
            outcome=outcome,
            http_status=http_status,
            latency_ms=latency_ms,
            error=None,
            terminal_status="delivered",
            next_attempt_at=None,
            failure_reason=None,
        )
        return {
            "batch_id": batch_id,
            "delivery_id": delivery_id,
            "status": "delivered",
            "http_status": http_status,
        }

    # Failure path — schedule retry or dead-letter.
    if job_try >= _MAX_ATTEMPTS:
        await _record_attempt(
            delivery_id=delivery_id,
            attempt_num=job_try,
            outcome=outcome,
            http_status=http_status,
            latency_ms=latency_ms,
            error=error,
            terminal_status="delivery_failed",
            next_attempt_at=None,
            failure_reason=(
                f"max attempts exhausted (last outcome={outcome}, "
                f"http_status={http_status}, error={error})"
            ),
        )
        return {
            "batch_id": batch_id,
            "delivery_id": delivery_id,
            "status": "delivery_failed",
        }

    # Pick the wait-before-next-attempt delay (off-by-one safe; see the
    # _RETRY_DELAYS_SECONDS comment block at module top).
    next_delay = _RETRY_DELAYS_SECONDS[job_try - 1]
    next_at = datetime.now(timezone.utc) + timedelta(seconds=next_delay)
    await _record_attempt(
        delivery_id=delivery_id,
        attempt_num=job_try,
        outcome=outcome,
        http_status=http_status,
        latency_ms=latency_ms,
        error=error,
        terminal_status=None,
        next_attempt_at=next_at,
        failure_reason=None,
    )
    # arq.worker.Retry is the documented signal to reschedule with a
    # specific deferral. Using a custom exception class would fall
    # through to arq's default exponential backoff (1s, 2s, 4s, …),
    # which does not match ADR 0035's 30s/2min/10min/1hr/6hr window.
    raise Retry(defer=next_delay)


async def _find_pending_delivery(
    *, batch_id: str, event_type: str
) -> str | None:
    """Return the delivery_id of an in-flight delivery, if any."""

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        stmt = (
            select(WebhookDelivery)
            .where(WebhookDelivery.batch_id == batch_id)
            .where(WebhookDelivery.event_type == event_type)
            .where(WebhookDelivery.status == "pending")
            .order_by(WebhookDelivery.created_at.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        return row.delivery_id if row is not None else None
