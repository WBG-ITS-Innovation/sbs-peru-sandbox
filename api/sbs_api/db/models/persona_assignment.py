"""PersonaAssignment — lightweight in-cockpit cross-persona handoff.

A Supervisor or Unit Head can "send to Lucía for a deeper look" on a
pattern, complaint, or FIBrief. That creates one row here, which shows
up in the target persona's "assigned to me" inbox. The Analyst can
acknowledge. No email/Slack — in-cockpit only (external notifications
deferred to a later prompt).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base

ASSIGNMENT_REF_TYPES = ("PATTERN", "COMPLAINT", "FIBRIEF")


class PersonaAssignment(Base):
    __tablename__ = "persona_assignments"

    assignment_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    source_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_persona: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_type: Mapped[str] = mapped_column(String(16), nullable=False)
    ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "ref_type IN ('PATTERN','COMPLAINT','FIBRIEF')",
            name="ck_persona_assignments_ref_type",
        ),
        Index(
            "ix_persona_assignments_target_ack",
            "target_user_id",
            "acknowledged_at",
        ),
    )
