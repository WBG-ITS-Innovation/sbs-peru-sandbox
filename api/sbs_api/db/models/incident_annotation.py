"""IncidentAnnotation — SBS IT operational incident notes (P-RESHAPE-8.5).

Rosa's one write action: annotate an operational incident (e.g. "webhook
delivery degraded 10:00–10:20, upstream TLS handshake errors"). Ops-only
by construction — this table carries NO business field. Remediation
actions (retry, requeue, circuit-break) are deferred to P-RESHAPE-9.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class IncidentAnnotation(Base):
    __tablename__ = "incident_annotations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Operational component the note concerns (e.g. "webhook_delivery",
    # "ingestion", "agent_runtime"). Not a business field.
    component: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_incident_annotations_created", "created_at"),
    )
