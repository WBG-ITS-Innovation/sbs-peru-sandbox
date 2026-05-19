"""Per-institution HMAC secrets — ADR 0027 amendment.

Each institution has at most one row. The ``active_secret`` is the one
the institution is currently signing with; ``previous_secret`` is the
prior value held during a rotation grace window so in-flight requests
signed with the old secret continue to validate. Both columns store the
secret in raw form for the sandbox; production overlay wraps them with
the KMS-encrypted column type when the secret store lands in Part 8.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class InstitutionSecret(Base):
    __tablename__ = "institution_secrets"

    institution_id: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("institutions.institution_id"),
        primary_key=True,
    )
    active_secret: Mapped[bytes] = mapped_column(LargeBinary(length=64), nullable=False)
    previous_secret: Mapped[bytes | None] = mapped_column(
        LargeBinary(length=64), nullable=True
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
