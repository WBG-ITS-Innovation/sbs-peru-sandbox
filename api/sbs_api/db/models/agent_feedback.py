"""Agent feedback — what the model learns from human correction.

Two cases land rows here:

* ``decision='reject'`` — the Conduct Unit Head rejected the finding. The rationale
  carries the head's explanation; no edit_diff (the agent's draft did
  not contribute to a supervisory observation).
* ``decision='approve-with-edits'`` — the agent's draft was approved
  with the head's modifications. The edit_diff captures before/after
  so the model-tuning pipeline (Part 10 AI eval) can learn from the
  correction.

The send-back-to-analyst decision does NOT land here — it's a
workflow handoff, not feedback. The corresponding ``pending_approvals``
row transitions to ``status='sent_back'`` instead.
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class AgentFeedback(Base):
    __tablename__ = "agent_feedback"

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

    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)

    # JSON {before: str, after: str} when decision='approve-with-edits';
    # null on plain reject (no observation row paired with it).
    edit_diff: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    recorded_by: Mapped[str] = mapped_column(String(128), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "decision IN ('reject', 'approve-with-edits')",
            name="ck_agent_feedback_decision",
        ),
        CheckConstraint(
            "char_length(rationale) >= 20",
            name="ck_agent_feedback_rationale_min_length",
        ),
        Index(
            "ix_agent_feedback_complaint_recorded",
            "complaint_id",
            "recorded_at",
        ),
        Index(
            "ix_agent_feedback_pending_approval",
            "pending_approval_id",
        ),
    )
