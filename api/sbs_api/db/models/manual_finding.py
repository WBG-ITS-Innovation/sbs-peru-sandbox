"""ManualFinding — analyst-proposed pattern (P-RESHAPE-8.5).

The Analyst's ``propose_pattern`` action: "I see something the automatic
analysis did not." Kept in its own table rather than written into
``pattern_detections`` so a human proposal never enters the automated
aggregation → investigation trigger path (which keys off detector-produced
rows). Downstream triage of manual proposals is deferred.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class ManualFinding(Base):
    __tablename__ = "manual_findings"

    finding_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    proposed_by_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    persona: Mapped[str] = mapped_column(String(48), nullable=False)
    institution_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="PROPOSED"
    )

    __table_args__ = (
        Index("ix_manual_findings_created", "created_at"),
    )
