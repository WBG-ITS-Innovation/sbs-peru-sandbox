# SPDX-License-Identifier: Apache-2.0
"""Narrative-draft history for complaints.

Every time Analyst edits the agent-drafted narrative on the Findings
drilldown, a new ``complaint_narrative_drafts`` row lands. The row
carries the before/after text so an auditor can reconstruct the edit
trail; the matching ``audit_events`` row (action='edit-draft-narrative')
ties the edit to the operator and to the session.

This table is append-only. There is no UPDATE path — every edit
creates a new row. The latest row by ``created_at`` is the "current"
draft for that complaint.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class ComplaintNarrativeDraft(Base):
    __tablename__ = "complaint_narrative_drafts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    complaint_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("complaints.complaint_id"), nullable=False
    )

    # The agent_run that produced the original drafted narrative. Null
    # when the draft is a pure human edit with no agent ancestor.
    agent_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_runs.id"), nullable=True
    )

    created_by: Mapped[str] = mapped_column(String(128), nullable=False)

    before_text: Mapped[str] = mapped_column(Text, nullable=False)
    after_text: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_complaint_narrative_drafts_complaint_id_created_at",
            "complaint_id",
            "created_at",
        ),
    )
