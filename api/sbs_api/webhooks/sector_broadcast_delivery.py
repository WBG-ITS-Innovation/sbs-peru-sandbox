"""Sector-broadcast outbound delivery (P-RESHAPE-6).

Reuses the existing signed-webhook chain (same HMAC signing as the FI
brief), but the payload shape differs and carries an
``X-Payload-Type: SECTOR_BROADCAST`` header so FI receivers can route it
separately from a bilateral brief.

Each recipient is delivered + tracked independently in
``sector_broadcast_deliveries``. Idempotent: re-running does NOT re-send
to a recipient already DELIVERED. The HTTP send is injectable (``sender``)
for testing without a live receiver.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.institution_webhook_config import InstitutionWebhookConfig
from sbs_api.db.models.outbound_webhook_secret import OutboundWebhookSecret
from sbs_api.db.models.sector_broadcast import (
    SectorBroadcast,
    SectorBroadcastDelivery,
)
from sbs_api.webhook.signing import (
    KID_SANDBOX_V1,
    build_outbound_canonical_request,
    compute_outbound_signature,
    signature_header,
)

log = logging.getLogger(__name__)

PAYLOAD_TYPE_HEADER = "X-Payload-Type"
PAYLOAD_TYPE = "SECTOR_BROADCAST"
MAX_ATTEMPTS = 3

Sender = Callable[[httpx.Request], Awaitable[tuple[int, str]]]


@dataclass(frozen=True)
class BroadcastDeliveryOutcome:
    broadcast_id: str
    status: str
    delivered: int
    failed: int
    skipped_already_delivered: int


async def _default_sender(request: httpx.Request) -> tuple[int, str]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.send(request)
        return resp.status_code, resp.text


def build_broadcast_payload(broadcast: SectorBroadcast, target_fi: str) -> dict:
    return {
        "event": "sector.fraud.broadcast",
        "broadcast_id": broadcast.broadcast_id,
        "target_institution_id": target_fi,
        "origin_fi_anonymized": True,
        "threat_summary_es": broadcast.threat_summary_es,
        "threat_summary_en": broadcast.threat_summary_en,
        "threat_indicators": list(broadcast.threat_indicators),
        "suggested_controls": list(broadcast.suggested_controls),
        "urgency": broadcast.urgency,
        "response_deadline": broadcast.response_deadline.astimezone(
            timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _signed_request(
    *, callback_url: str, payload_json: str, institution_id: str, secret: bytes
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
        PAYLOAD_TYPE_HEADER: PAYLOAD_TYPE,
    }
    return httpx.Request("POST", callback_url, content=body, headers=headers)


async def _deliver_one(
    session: AsyncSession,
    *,
    broadcast: SectorBroadcast,
    target_fi: str,
    sender: Sender,
) -> str:
    """Deliver to one recipient; returns the per-recipient status."""
    delivery = (
        await session.execute(
            select(SectorBroadcastDelivery).where(
                SectorBroadcastDelivery.broadcast_id == broadcast.broadcast_id,
                SectorBroadcastDelivery.target_fi_code == target_fi,
            )
        )
    ).scalar_one_or_none()
    if delivery is None:
        delivery = SectorBroadcastDelivery(
            broadcast_id=broadcast.broadcast_id,
            target_fi_code=target_fi,
            status="PENDING",
            attempts=0,
        )
        session.add(delivery)
        await session.flush()

    # Idempotency: never re-send to an already-DELIVERED recipient.
    if delivery.status == "DELIVERED":
        return "DELIVERED"

    config = (
        await session.execute(
            select(InstitutionWebhookConfig).where(
                InstitutionWebhookConfig.institution_id == target_fi
            )
        )
    ).scalar_one_or_none()
    secret_row = (
        await session.execute(
            select(OutboundWebhookSecret).where(
                OutboundWebhookSecret.institution_id == target_fi
            )
        )
    ).scalar_one_or_none()
    if config is None or not config.enabled or secret_row is None:
        delivery.status = "DELIVERY_FAILED"
        await session.flush()
        return "DELIVERY_FAILED"

    payload_json = json.dumps(
        build_broadcast_payload(broadcast, target_fi), separators=(",", ":")
    )
    delivery.sent_at = datetime.now(tz=timezone.utc)
    final = "DELIVERY_FAILED"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        delivery.attempts = attempt
        request = _signed_request(
            callback_url=config.callback_url,
            payload_json=payload_json,
            institution_id=target_fi,
            secret=bytes(secret_row.active_secret),
        )
        try:
            status_code, _ = await sender(request)
        except Exception:  # noqa: BLE001
            status_code = 0
        if 200 <= status_code < 300:
            delivery.status = "DELIVERED"
            delivery.delivered_at = datetime.now(tz=timezone.utc)
            final = "DELIVERED"
            break
    else:
        delivery.status = "DELIVERY_FAILED"
    await session.flush()
    return final


async def deliver_sector_broadcast(
    session: AsyncSession,
    *,
    broadcast_id: str,
    sender: Sender | None = None,
) -> BroadcastDeliveryOutcome:
    """Deliver an APPROVED broadcast to every target FI. Per-recipient
    idempotent. Sets the broadcast to DELIVERED (all ok) /
    PARTIALLY_DELIVERED (some failed)."""
    sender = sender or _default_sender
    broadcast = (
        await session.execute(
            select(SectorBroadcast).where(
                SectorBroadcast.broadcast_id == broadcast_id
            )
        )
    ).scalar_one_or_none()
    if broadcast is None:
        raise ValueError(f"SectorBroadcast {broadcast_id} not found")
    # DELIVERED is included so a re-run is a safe no-op at the recipient
    # level (per-recipient idempotency reports them as skipped rather
    # than re-sending).
    if broadcast.status not in {
        "APPROVED",
        "DELIVERING",
        "PARTIALLY_DELIVERED",
        "DELIVERED",
    }:
        log.info(
            "deliver_sector_broadcast no-op broadcast_id=%s status=%s",
            broadcast_id,
            broadcast.status,
        )
        return BroadcastDeliveryOutcome(broadcast_id, broadcast.status, 0, 0, 0)

    broadcast.status = "DELIVERING"
    await session.flush()

    delivered = 0
    failed = 0
    skipped = 0
    for target_fi in broadcast.target_fi_codes:
        # Pre-check for the skipped counter.
        existing = (
            await session.execute(
                select(SectorBroadcastDelivery).where(
                    SectorBroadcastDelivery.broadcast_id == broadcast_id,
                    SectorBroadcastDelivery.target_fi_code == target_fi,
                )
            )
        ).scalar_one_or_none()
        if existing is not None and existing.status == "DELIVERED":
            skipped += 1
            continue
        status = await _deliver_one(
            session, broadcast=broadcast, target_fi=target_fi, sender=sender
        )
        if status == "DELIVERED":
            delivered += 1
        else:
            failed += 1

    broadcast.status = "DELIVERED" if failed == 0 else "PARTIALLY_DELIVERED"
    await session.flush()
    return BroadcastDeliveryOutcome(
        broadcast_id, broadcast.status, delivered, failed, skipped
    )
