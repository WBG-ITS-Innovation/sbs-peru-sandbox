"""Batch manifest ORM model.

The full Tier 2 ingestion pipeline lands in Prompt 8; this prompt scaffolds
the manifest record and the status fields the GET endpoints need to return
a coherent state today.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class BatchRecord(Base):
    __tablename__ = "batches"

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("institutions.institution_id"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reporting_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    reporting_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    row_count_submitted: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count_accepted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    row_count_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_upload")
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_batches_institution_submitted_at", "institution_id", "submitted_at"),
    )
