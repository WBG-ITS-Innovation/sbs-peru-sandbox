"""Per-institution outbound webhook callback configuration (ADR 0035).

One row per institution at most. ``event_type`` is deliberately absent
(YAGNI per the spec; revisit in Prompt 12 when agent-emitted events
actually need event-type routing). For now every event the SBS API emits
about a given institution's batches goes to the institution's single
callback URL.

Registration is out-of-band: SBS analysts insert rows via dev seed or
(post-Part 8) the admin API. There is no institution-facing endpoint to
self-register a webhook URL.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class InstitutionWebhookConfig(Base):
    __tablename__ = "institution_webhook_configs"

    institution_id: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("institutions.institution_id"),
        primary_key=True,
    )
    callback_url: Mapped[str] = mapped_column(String(512), nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
