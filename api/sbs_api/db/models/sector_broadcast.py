# SPDX-License-Identifier: Apache-2.0
"""Sector-broadcast ORM models — the sector-level fraud-warning surface.

Three tables, created together by migration ``20260528_0005``:

* ``sector_broadcasts`` — one warning derived from a ``pattern_detections``
  row, carrying the dual-approval trail (primary + secondary approver,
  each with rationale) and the anonymisation flag that keeps the
  originating institution out of what the sector receives.
* ``sector_broadcast_deliveries`` — per-recipient delivery tracking, one
  row per (broadcast, target FI); the unique index is what makes a
  redelivery an update rather than a duplicate.
* ``sector_broadcast_audit`` — append-only event log per broadcast.

These models were written **after** the migration and conform to it
exactly; they add no schema of their own. They exist because the tables
had no model at all, which left them invisible to ``Base.metadata`` —
absent from any ``create_all`` test schema, and, worse, read by Alembic
autogenerate as tables to DROP. See
docs/audit/2026-08-11-f10-report.md.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from sbs_api.db.base import Base


class SectorBroadcast(Base):
    __tablename__ = "sector_broadcasts"

    broadcast_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    origin_pattern_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pattern_detections.pattern_id"), nullable=False
    )
    # The sector sees the threat, not who reported it.
    origin_fi_anonymized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    target_fi_codes: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(String(16)), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    threat_summary_es: Mapped[str] = mapped_column(Text(), nullable=False)
    threat_summary_en: Mapped[str | None] = mapped_column(Text(), nullable=True)
    threat_indicators: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(String(40)), nullable=False
    )
    suggested_controls: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(String(40)), nullable=False
    )
    urgency: Mapped[str] = mapped_column(String(16), nullable=False)
    response_deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Dual approval: nothing reaches the sector on one supervisor's say-so.
    requires_dual_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    primary_approver: Mapped[str | None] = mapped_column(String(128), nullable=True)
    primary_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    primary_rationale: Mapped[str | None] = mapped_column(Text(), nullable=True)
    secondary_approver: Mapped[str | None] = mapped_column(String(128), nullable=True)
    secondary_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    secondary_rationale: Mapped[str | None] = mapped_column(Text(), nullable=True)
    rejected_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    model_id: Mapped[str] = mapped_column(String(96), nullable=False)
    model_provider: Mapped[str] = mapped_column(String(16), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','AWAITING_DUAL_APPROVAL',"
            "'AWAITING_SECONDARY_APPROVAL','APPROVED','DELIVERING',"
            "'DELIVERED','PARTIALLY_DELIVERED','REJECTED')",
            name="ck_sector_broadcasts_status",
        ),
        CheckConstraint(
            "urgency IN ('ROUTINE','ELEVATED','CRITICAL')",
            name="ck_sector_broadcasts_urgency",
        ),
        Index(
            "ix_sector_broadcasts_status_created",
            "status",
            "created_at",
        ),
    )


class SectorBroadcastDelivery(Base):
    __tablename__ = "sector_broadcast_deliveries"

    delivery_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    broadcast_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sector_broadcasts.broadcast_id"), nullable=False
    )
    target_fi_code: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ix_sector_broadcast_deliveries_broadcast_target",
            "broadcast_id",
            "target_fi_code",
            unique=True,
        ),
    )


class SectorBroadcastAudit(Base):
    __tablename__ = "sector_broadcast_audit"

    event_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    broadcast_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sector_broadcasts.broadcast_id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text(), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_sector_broadcast_audit_broadcast_occurred",
            "broadcast_id",
            "occurred_at",
        ),
    )
