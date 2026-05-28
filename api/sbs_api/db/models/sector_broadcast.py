"""SectorBroadcast ORM model — sector-level fraud warning (P-RESHAPE-6).

When a FRAUD_EMERGENCE pattern is confirmed HIGH against one FI
(``origin_fi`` — never named in the broadcast), SBS warns the rest of
that FI's cohort before they're hit. A broadcast is a sector-level
policy action: it carries a **dual-approval** gate (two distinct
approvers, the second a Unit Head or Superintendent) because misuse
damages SBS's relationship with the whole sector at once.

Status lifecycle:
    DRAFT → AWAITING_DUAL_APPROVAL → AWAITING_SECONDARY_APPROVAL
          → APPROVED → DELIVERING → DELIVERED | PARTIALLY_DELIVERED
          → REJECTED
Per-recipient delivery is tracked in ``sector_broadcast_deliveries``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base

SECTOR_BROADCAST_STATUSES = (
    "DRAFT",
    "AWAITING_DUAL_APPROVAL",
    "AWAITING_SECONDARY_APPROVAL",
    "APPROVED",
    "DELIVERING",
    "DELIVERED",
    "PARTIALLY_DELIVERED",
    "REJECTED",
)

SUGGESTED_CONTROLS = (
    "REVIEW_FEE_DISCLOSURE_FLOWS",
    "STRENGTHEN_FRAUD_MONITORING",
    "AUDIT_DIGITAL_ONBOARDING",
    "NOTIFY_CUSTOMERS",
    "INCREASE_SLA_VIGILANCE",
)

URGENCY_LEVELS = ("ROUTINE", "ELEVATED", "CRITICAL")


class SectorBroadcast(Base):
    __tablename__ = "sector_broadcasts"

    broadcast_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    origin_pattern_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pattern_detections.pattern_id"),
        nullable=False,
    )
    # Always true — the attacked FI is NEVER named in the broadcast.
    origin_fi_anonymized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    target_fi_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")

    threat_summary_es: Mapped[str] = mapped_column(Text, nullable=False)
    threat_summary_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    threat_indicators: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), nullable=False
    )
    suggested_controls: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), nullable=False
    )
    urgency: Mapped[str] = mapped_column(String(16), nullable=False)
    response_deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    requires_dual_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Dual-approval bookkeeping.
    primary_approver: Mapped[str | None] = mapped_column(String(128), nullable=True)
    primary_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    primary_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    secondary_approver: Mapped[str | None] = mapped_column(String(128), nullable=True)
    secondary_approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    secondary_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        Index("ix_sector_broadcasts_status_created", "status", "created_at"),
    )


class SectorBroadcastDelivery(Base):
    __tablename__ = "sector_broadcast_deliveries"

    delivery_id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True
    )
    broadcast_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sector_broadcasts.broadcast_id"),
        nullable=False,
    )
    target_fi_code: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="PENDING"
    )
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
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

    event_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    broadcast_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sector_broadcasts.broadcast_id"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
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
