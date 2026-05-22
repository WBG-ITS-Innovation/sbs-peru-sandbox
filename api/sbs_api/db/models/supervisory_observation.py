"""Supervisory observation — the official record an Approval creates.

When Jorge approves (or approves-with-edits) a finding, the head's
final narrative lands here. WS6's audit screen joins on
``approved_at`` + ``approved_by`` to render the decision chain;
production SBS workflows would also flow this row to the
institution-notification layer.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class SupervisoryObservation(Base):
    __tablename__ = "supervisory_observations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    complaint_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("complaints.complaint_id"), nullable=False
    )
    agent_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_runs.id"), nullable=True
    )
    pending_approval_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pending_approvals.id"), nullable=False
    )

    # The narrative as approved — the same text Lucía edited (or the
    # head's further edit when approve-with-edits is chosen).
    narrative: Mapped[str] = mapped_column(Text, nullable=False)

    approved_by: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    agent_version: Mapped[str | None] = mapped_column(String(96), nullable=True)
    model_versions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index(
            "ix_supervisory_observations_complaint_approved",
            "complaint_id",
            "approved_at",
        ),
        Index(
            "ix_supervisory_observations_pending_approval",
            "pending_approval_id",
        ),
    )
