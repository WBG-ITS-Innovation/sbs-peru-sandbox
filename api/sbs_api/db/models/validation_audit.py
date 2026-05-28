"""DIValeVale validation storage (P-RESHAPE-8).

Three tables:
* ``validation_audit`` — one row per record DIValeVale evaluated, with
  the verdict, which Pass-1 rules failed, what Pass-2 recovered, and the
  routing action. References IDs + codes only — never narrative text.
* ``validation_batches`` — Tier-2 batch-level state + diagnostic report.
* ``enrichment_requests`` — Tier-1 enrichment cycle tracking.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base

VERDICTS = ("VALID", "RECOVERABLE", "INSUFFICIENT", "INVALID")
ROUTING_ACTIONS = (
    "PROCEEDED_TO_TRIAGE",
    "QUARANTINED_BATCH",
    "FLAGGED_FOR_ENRICHMENT",
    "REJECTED",
)
TIERS = ("TIER_1", "TIER_2")
BATCH_STATES = ("PROCESSING", "QUARANTINED", "ACCEPTED", "REPLACED")
ENRICHMENT_STATES = ("PENDING", "FULFILLED", "EXPIRED", "ESCALATED")


class ValidationAudit(Base):
    __tablename__ = "validation_audit"

    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    complaint_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    institution_code: Mapped[str] = mapped_column(String(32), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    pass1_failed_rules: Mapped[list[str]] = mapped_column(
        ARRAY(String(48)), nullable=False
    )
    pass2_invoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    pass2_recoveries: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    pass2_model_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    routing_action: Mapped[str] = mapped_column(String(32), nullable=False)
    batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_id: Mapped[str] = mapped_column(String(96), nullable=False)
    model_provider: Mapped[str] = mapped_column(String(16), nullable=False)
    tier: Mapped[str] = mapped_column(String(8), nullable=False)
    latency_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    __table_args__ = (
        CheckConstraint(
            "verdict IN ('VALID','RECOVERABLE','INSUFFICIENT','INVALID')",
            name="ck_validation_audit_verdict",
        ),
        CheckConstraint(
            "routing_action IN ('PROCEEDED_TO_TRIAGE','QUARANTINED_BATCH',"
            "'FLAGGED_FOR_ENRICHMENT','REJECTED')",
            name="ck_validation_audit_routing",
        ),
        CheckConstraint(
            "tier IN ('TIER_1','TIER_2')", name="ck_validation_audit_tier"
        ),
        Index("ix_validation_audit_institution_received", "institution_code", "received_at"),
        Index("ix_validation_audit_verdict_received", "verdict", "received_at"),
        Index("ix_validation_audit_batch", "batch_id"),
    )


class ValidationBatch(Base):
    __tablename__ = "validation_batches"

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_code: Mapped[str] = mapped_column(String(32), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recoverable_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    insufficient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    diagnostic_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    replaced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replaced_by_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "state IN ('PROCESSING','QUARANTINED','ACCEPTED','REPLACED')",
            name="ck_validation_batches_state",
        ),
        Index("ix_validation_batches_institution", "institution_code", "received_at"),
    )


class EnrichmentRequest(Base):
    __tablename__ = "enrichment_requests"

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    complaint_id: Mapped[str] = mapped_column(String(32), nullable=False)
    institution_code: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    missing_fields: Mapped[list[str]] = mapped_column(
        ARRAY(String(48)), nullable=False
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    fulfilled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fulfilled_via_complaint_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    delivery_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PENDING"
    )
    delivery_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    __table_args__ = (
        CheckConstraint(
            "state IN ('PENDING','FULFILLED','EXPIRED','ESCALATED')",
            name="ck_enrichment_requests_state",
        ),
        Index("ix_enrichment_requests_complaint", "complaint_id"),
        Index("ix_enrichment_requests_state", "state", "deadline"),
    )
