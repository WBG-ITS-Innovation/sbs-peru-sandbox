"""PersonaAudit — append-only log of every persona action.

Distinct from the existing ``audit_events`` complaint-chain log: this
table records *who, in which persona, did what* across the cockpit —
including view-only ops queries (SBS IT) and cross-persona overrides
(Unit Head overriding a Supervisor decision, which carries a stricter
50-char rationale). Append-only; never updated or deleted.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class PersonaAudit(Base):
    __tablename__ = "persona_audit"

    event_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    persona: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Sanitised parameters only — never a business payload (IT ops
    # queries are logged with their filter args, not their results).
    params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_persona_audit_actor_occurred", "actor_user_id", "occurred_at"),
        Index("ix_persona_audit_action_occurred", "action", "occurred_at"),
    )
