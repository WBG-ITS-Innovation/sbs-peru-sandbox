"""FIBrief ORM model — pre-escalation feedback brief sent to an FI.

When Peer Risk Radar flags an institution as a sustained HIGH-severity
outlier, the Issue Resurface agent drafts a structured brief that —
after supervisor approval — is delivered to the FI's conduct officer
over the existing signed outbound-webhook channel. This is *pre*-
escalation: it gives the FI a chance to self-correct before formal
supervisory action.

Status lifecycle:

    DRAFT → AWAITING_APPROVAL → APPROVED → PENDING → SENT
          → DELIVERED → ACKED
                       ↘ DELIVERY_FAILED
    AWAITING_APPROVAL → REJECTED   (supervisor declines)

Provenance (``model_id`` + ``model_provider``) is mandatory — the
brief is institution-facing, so which model produced the narrative is
not optional.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base

FI_BRIEF_STATUSES = (
    "DRAFT",
    "AWAITING_APPROVAL",
    "APPROVED",
    "REJECTED",
    "PENDING",
    "SENT",
    "DELIVERED",
    "DELIVERY_FAILED",
    "ACKED",
)

# Remediation areas are a FIXED enum — never LLM-generated.
REMEDIATION_AREAS = (
    "FEE_DISCLOSURE",
    "DIGITAL_CHANNEL_RELIABILITY",
    "FRAUD_CONTROLS",
    "COMPLAINT_HANDLING_SLA",
    "CONTRACT_TRANSPARENCY",
    "OTHER",
)


class FIBrief(Base):
    __tablename__ = "fi_briefs"

    brief_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    peer_risk_analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("peer_risk_analyses.analysis_id"),
        nullable=False,
    )
    pattern_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pattern_detections.pattern_id"),
        nullable=False,
    )
    institution_id: Mapped[str] = mapped_column(String(10), nullable=False)
    motivo_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="DRAFT"
    )

    pattern_summary_es: Mapped[str] = mapped_column(Text, nullable=False)
    pattern_summary_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    peer_context_es: Mapped[str] = mapped_column(Text, nullable=False)
    peer_context_en: Mapped[str | None] = mapped_column(Text, nullable=True)

    suggested_remediation_areas: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), nullable=False
    )
    response_deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    evidence_complaint_count: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    evidence_window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    evidence_window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Approval bookkeeping.
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approval_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejected_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Delivery bookkeeping.
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ack_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ack_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    delivery_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    model_id: Mapped[str] = mapped_column(String(96), nullable=False)
    model_provider: Mapped[str] = mapped_column(String(16), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','AWAITING_APPROVAL','APPROVED','REJECTED',"
            "'PENDING','SENT','DELIVERED','DELIVERY_FAILED','ACKED')",
            name="ck_fi_briefs_status",
        ),
        Index(
            "ix_fi_briefs_institution_motivo_created",
            "institution_id",
            "motivo_code",
            "created_at",
        ),
        Index("ix_fi_briefs_status_created", "status", "created_at"),
    )
