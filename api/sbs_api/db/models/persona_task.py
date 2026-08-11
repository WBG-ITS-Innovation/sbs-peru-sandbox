# SPDX-License-Identifier: Apache-2.0
"""PersonaTask ORM model — cross-persona work handoff.

One row per task a supervisor hands to another persona: a deeper look at
a complaint, a delegated pattern, an enrichment request, an FI-brief
review, a digest acknowledgement. ``ref_type`` / ``ref_id`` are a loose
pointer rather than a foreign key, because the referent varies by
``task_type`` (a complaint, a pattern, a broadcast).

Created by migration ``20260528_0008``. This model was written **after**
that migration and conforms to it exactly; it adds no schema of its own.
It exists because the table had no model at all, which left it invisible
to ``Base.metadata`` — absent from any ``create_all`` test schema, and
read by Alembic autogenerate as a table to DROP. See
docs/audit/2026-08-11-f10-report.md.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from sbs_api.db.base import Base


class PersonaTask(Base):
    __tablename__ = "persona_tasks"

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    created_by_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_persona: Mapped[str] = mapped_column(String(48), nullable=False)
    # Null while the task is addressed to a persona rather than a person.
    assigned_to_user_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    assigned_to_persona: Mapped[str] = mapped_column(String(48), nullable=False)

    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Loose pointer: the referent's table depends on task_type, so this is
    # deliberately not a foreign key.
    ref_type: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(Text(), nullable=False)

    state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'OPEN'")
    )
    acked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    declined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    response: Mapped[str | None] = mapped_column(Text(), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "task_type IN ('DEEPER_LOOK','PATTERN_DELEGATION',"
            "'ENRICHMENT_REQUEST','FI_BRIEF_REVIEW','DIGEST_ACK')",
            name="ck_persona_tasks_task_type",
        ),
        CheckConstraint(
            "state IN ('OPEN','ACKED','COMPLETED','DECLINED')",
            name="ck_persona_tasks_state",
        ),
        Index(
            "ix_persona_tasks_assignee_state",
            "assigned_to_user_id",
            "state",
        ),
        Index(
            "ix_persona_tasks_persona_state",
            "assigned_to_persona",
            "state",
        ),
        Index(
            "ix_persona_tasks_creator_created",
            "created_by_user_id",
            "created_at",
        ),
    )
