# SPDX-License-Identifier: Apache-2.0
"""Outbound webhook delivery record (ADR 0035).

One row per delivery target. The webhook signing/delivery worker reads
this table for retry scheduling and updates ``attempts``, ``status``,
``next_attempt_at``, and the JSON-encoded ``attempt_history``.

Status vocabulary:

* ``pending`` — created, no attempt yet, ``next_attempt_at`` set.
* ``delivering`` — an attempt is in flight (transient; worker writes
  this and clears it on attempt completion).
* ``delivered`` — institution returned 2xx; ``completed_at`` set.
* ``delivery_failed`` — final attempt failed (5 attempts exhausted, or
  URL validation rejected before any attempt). ``failure_reason``
  carries either the last HTTP status, the connection error, or the
  validation code (``WEBHOOK_URL_REJECTED``).

``attempt_history`` is a JSON-encoded list of objects, one per attempt:
``{"attempt_num": int, "started_at": iso8601, "http_status": int|null,
"latency_ms": int|null, "outcome": "delivered"|"http_error"|"connect_failed"
|"timeout"|"url_rejected", "error": str|null}``. The structlog event
``webhook.delivery.attempt`` mirrors these fields.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    delivery_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("batches.batch_id"), nullable=False
    )
    institution_id: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("institutions.institution_id"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_history: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]"
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_webhook_deliveries_batch_id", "batch_id"),
        Index(
            "ix_webhook_deliveries_status_next_attempt",
            "status",
            "next_attempt_at",
        ),
    )
