"""PersonaTask — the cockpit task inbox/outbox (P-RESHAPE-8.5).

Every persona sees tasks assigned to them (inbox) and tasks they have
created for others (outbox). A task carries a small state machine
(OPEN → ACKED → COMPLETED/DECLINED).

Relationship to ``persona_assignments`` (P-RESHAPE-5): that table is the
older, ack-only cross-persona handoff and remains the authoritative
record for the ``/v1/internal/persona/assignments`` surface. ``persona_tasks``
is the authoritative record for the P-RESHAPE-8.5 action surface — the
verbs that create tasking (``request_deeper_look`` → DEEPER_LOOK,
``delegate_pattern`` → PATTERN_DELEGATION). The two are not joined; new
action-surface code writes here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base

TASK_TYPES = (
    "DEEPER_LOOK",
    "PATTERN_DELEGATION",
    "ENRICHMENT_REQUEST",
    "FI_BRIEF_REVIEW",
    "DIGEST_ACK",
)
TASK_STATES = ("OPEN", "ACKED", "COMPLETED", "DECLINED")


class PersonaTask(Base):
    __tablename__ = "persona_tasks"

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_persona: Mapped[str] = mapped_column(String(48), nullable=False)
    # Null target_user_id means "any persona of type assigned_to_persona".
    assigned_to_user_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    assigned_to_persona: Mapped[str] = mapped_column(String(48), nullable=False)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_type: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="OPEN"
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
    response: Mapped[str | None] = mapped_column(Text, nullable=True)

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
        Index("ix_persona_tasks_assignee_state", "assigned_to_user_id", "state"),
        Index("ix_persona_tasks_persona_state", "assigned_to_persona", "state"),
        Index("ix_persona_tasks_creator_created", "created_by_user_id", "created_at"),
    )
