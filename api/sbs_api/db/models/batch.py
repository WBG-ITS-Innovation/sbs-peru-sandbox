# SPDX-License-Identifier: Apache-2.0
"""Batch ORM model (Tier 2 ingestion).

The ``batches`` table holds one row per batch upload. The 4-state machine
(``pending`` → ``processing`` → ``complete`` | ``failed``) lives in
:mod:`sbs_api.batch.state` and is the canonical state vocabulary for
Prompt 8; the column carries the string value.

``file_path`` is the on-disk location the route handler wrote the CSV to
on accept. The worker reads from this path; the prune job (Workstream F.2)
deletes files older than ``settings.batch_storage_prune_days``.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
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
    row_count_accepted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    row_count_rejected: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ix_batches_institution_submitted_at",
            "institution_id",
            "submitted_at",
        ),
    )
