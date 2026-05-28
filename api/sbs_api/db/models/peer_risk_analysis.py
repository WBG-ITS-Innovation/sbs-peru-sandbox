"""PeerRiskAnalysis ORM model.

One row per (pattern_id, run). Persisted so the cockpit drilldown
can re-render the analysis without re-running the LLM call, and so
provenance (model_id + model_provider) is queryable for audit.

``model_provider`` is constrained to ``'onprem'`` in v1 — the
Peer Risk Radar narrative is the first agent surface that ships with
a hard "no cloud" stance until ``SBS_API_CLOUD_LEGAL_APPROVED``
opens the path.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class PeerRiskAnalysis(Base):
    __tablename__ = "peer_risk_analyses"

    analysis_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pattern_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pattern_detections.pattern_id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    cohort_id: Mapped[str] = mapped_column(String(32), nullable=False)
    peer_count: Mapped[int] = mapped_column(Integer, nullable=False)
    percentile: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    z_score: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 3), nullable=True
    )
    is_outlier: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    forecast: Mapped[dict] = mapped_column(JSONB, nullable=False)
    narrative_es: Mapped[str] = mapped_column(Text, nullable=False)
    narrative_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_id: Mapped[str] = mapped_column(String(96), nullable=False)
    model_provider: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "model_provider IN ('onprem','replay','mock','template')",
            name="ck_peer_risk_analyses_model_provider",
        ),
        Index("ix_peer_risk_analyses_pattern_id", "pattern_id"),
        Index(
            "ix_peer_risk_analyses_cohort_created",
            "cohort_id",
            "created_at",
        ),
    )
