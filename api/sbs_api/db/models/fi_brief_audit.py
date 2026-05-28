"""FIBriefAudit — append-only event log for every FIBrief transition.

One row per state change (drafted, submitted-for-approval, approved,
rejected, edit-applied, delivery-attempt, delivered, acked). The
cockpit decision-history panel and the WS6 audit screen read this.
Append-only: rows are never updated or deleted.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class FIBriefAudit(Base):
    __tablename__ = "fi_brief_audit"

    event_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    brief_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("fi_briefs.brief_id"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    event_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_fi_brief_audit_brief_id_occurred", "brief_id", "occurred_at"),
    )
