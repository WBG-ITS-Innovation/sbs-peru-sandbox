# SPDX-License-Identifier: Apache-2.0
"""Pending-approvals queue.

When Lucía clicks "Send to Approvals" on a Findings drilldown, a row
lands here in status='pending'. WS5's Approvals screen reads this
table to populate Jorge's queue. The decision endpoints (approve /
approve-with-edits / reject / send-back) update the same row's status
+ decided_at + decided_by + decision_rationale.

Idempotency is application-level: the route handler checks whether a
pending row already exists for the (complaint_id, agent_run_id) pair
and short-circuits if so. A unique constraint is not enforced at the
DB level because the same complaint may legitimately be re-sent after
a prior rejection.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class PendingApproval(Base):
    __tablename__ = "pending_approvals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    complaint_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("complaints.complaint_id"), nullable=False
    )

    agent_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_runs.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)

    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'sent_back')",
            name="ck_pending_approvals_status",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_pending_approvals_severity",
        ),
        Index(
            "ix_pending_approvals_status_created_at",
            "status",
            "created_at",
        ),
        Index("ix_pending_approvals_complaint_id", "complaint_id"),
    )
