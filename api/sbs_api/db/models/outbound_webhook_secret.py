"""Per-institution outbound HMAC secret (ADR 0035).

Distinct table from :class:`InstitutionSecret` (inbound) so the two
secret namespaces rotate independently. The ``kid`` column carries the
key identifier echoed in the outbound ``X-SBS-Key-Id`` header; value is
``sandbox-v1`` for every row landed by Prompt 8. Future rotation will
move the active secret to ``previous_secret`` with a retire-at deadline
and rotate the ``kid`` (e.g. ``sandbox-v2``); the rotation reader logic
lands with the Part 8 admin work.

Shape mirrors ``institution_secrets`` so the verification recipe SDK
writers will document is symmetric in/out of the API.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class OutboundWebhookSecret(Base):
    __tablename__ = "outbound_webhook_secrets"

    institution_id: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("institutions.institution_id"),
        primary_key=True,
    )
    kid: Mapped[str] = mapped_column(
        String(32), nullable=False, default="sandbox-v1"
    )
    active_secret: Mapped[bytes] = mapped_column(
        LargeBinary(64), nullable=False
    )
    previous_secret: Mapped[bytes | None] = mapped_column(
        LargeBinary(64), nullable=True
    )
    previous_secret_retires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rotated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
