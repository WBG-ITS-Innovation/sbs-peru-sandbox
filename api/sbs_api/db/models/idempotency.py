"""Idempotency-Key cache.

ADR 0029 locks the policy: 24-hour TTL, body-hash on store, 409 on replay
with a different body, replay returns the cached response with header
``Idempotency-Replayed: true``. The sweep job lives in Prompt 7.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    # Surrogate primary key. UUID v7 hex (stringified) so rows are naturally
    # time-ordered for the sweep job.
    record_id: Mapped[str] = mapped_column(String(32), primary_key=True)

    institution_id: Mapped[str] = mapped_column(String(10), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    body_sha256: Mapped[bytes] = mapped_column(LargeBinary(length=32), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_payload: Mapped[str] = mapped_column(Text, nullable=False)
    response_headers: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    request_method: Mapped[str] = mapped_column(String(8), nullable=False)
    request_path: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_idem_institution_key",
            "institution_id",
            "idempotency_key",
            unique=True,
        ),
        Index("ix_idem_expires_at", "expires_at"),
    )
