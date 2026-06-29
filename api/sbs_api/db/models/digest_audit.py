# SPDX-License-Identifier: Apache-2.0
"""DigestAudit — weekly executive digest lifecycle (P-RESHAPE-8.5).

Two events land here:
* GENERATED — the Unit Head (Jorge) generates a weekly digest.
* ACKNOWLEDGED — the Superintendent (Sergio) signs it.

Append-only. The digest *content* is summary-level only (counts and
plain-language lines); per the exec data-protection rule, no per-complaint
identifier or raw narrative is stored here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base

DIGEST_EVENTS = ("GENERATED", "ACKNOWLEDGED")


class DigestAudit(Base):
    __tablename__ = "digest_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Stable id for one digest; the GENERATED and ACKNOWLEDGED rows share it.
    digest_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    persona: Mapped[str] = mapped_column(String(48), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Summary-level only — never a per-complaint field.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('GENERATED','ACKNOWLEDGED')",
            name="ck_digest_audit_event_type",
        ),
        Index("ix_digest_audit_digest", "digest_id", "occurred_at"),
    )
