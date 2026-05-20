"""Per-row rejection detail for Tier 2 batch processing.

One row per failed row in a batch CSV. Populated by the arq worker
(:mod:`sbs_api.workers.batch_worker`) on validation failure. ``rule`` and
``message`` mirror the :class:`ProblemFieldError` shape so the GET
``/v1/batches/{batch_id}/rejections`` endpoint can return them under the
same envelope as Tier 1 RFC 9457 validation errors.

``raw_row_excerpt`` is the first ~500 chars of the original CSV row, kept
as a debugging breadcrumb. The full row is not stored — the CSV file on
disk is the authoritative copy until the prune job retires it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class BatchRowRejection(Base):
    __tablename__ = "batch_row_rejections"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    batch_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("batches.batch_id"), nullable=False
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    field: Mapped[str | None] = mapped_column(String(200), nullable=True)
    rule: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_row_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_batch_row_rejections_batch_id", "batch_id"),
        Index(
            "ix_batch_row_rejections_batch_row", "batch_id", "row_index"
        ),
    )
