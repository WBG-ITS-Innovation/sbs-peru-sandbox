"""PatternDetection ORM model.

One row per (pattern_type, institution, category, window) the
aggregation tick emitted. The Investigation orchestrator gates on
``severity_band == 'HIGH' AND triggered_investigation == false``; on
fire it sets ``triggered_investigation = true`` + the resulting
``investigation_run_id`` atomically under a Postgres advisory lock
keyed on ``pattern_id``.

Columns mirror P-RESHAPE-2 §2:

* ``contributing_complaint_ids`` — TEXT[] of the complaint IDs that
  fed the bucket count. The cockpit drilldown lists them.
* ``contributing_indecopi_case_ids`` — TEXT[] for the cross-source
  rule. NULL for the three single-source rules.
* ``composite_breakdown`` — JSONB carrying every weighted input the
  cockpit's explanation panel needs (locked weights, per-channel
  sub-score, the proxy-channel flag list, and the raw aggregation
  inputs).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Numeric,
    String,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class PatternDetection(Base):
    __tablename__ = "pattern_detections"

    pattern_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    institution_code: Mapped[str] = mapped_column(String(16), nullable=False)
    complaint_category: Mapped[str] = mapped_column(String(64), nullable=False)
    pattern_type: Mapped[str] = mapped_column(String(32), nullable=False)

    severity_score: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False
    )
    severity_band: Mapped[str] = mapped_column(String(8), nullable=False)

    contributing_complaint_ids: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(String(32)),
        nullable=False,
    )
    contributing_indecopi_case_ids: Mapped[list[str] | None] = mapped_column(
        postgresql.ARRAY(String(64)),
        nullable=True,
    )
    composite_breakdown: Mapped[dict] = mapped_column(
        postgresql.JSONB(),
        nullable=False,
    )

    triggered_investigation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    investigation_run_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "pattern_type IN ('VOLUME_SPIKE','SUSTAINED_ELEVATION',"
            "'CROSS_SOURCE_CORRELATION','NEW_TOPIC_EMERGENCE','FRAUD_EMERGENCE')",
            name="ck_pattern_detections_pattern_type",
        ),
        CheckConstraint(
            "severity_band IN ('HIGH','MEDIUM','LOW')",
            name="ck_pattern_detections_severity_band",
        ),
        Index(
            "ix_pattern_detections_inst_cat_detected",
            "institution_code",
            "complaint_category",
            "detected_at",
        ),
        Index(
            "ix_pattern_detections_band_triggered",
            "severity_band",
            "triggered_investigation",
        ),
    )
