"""Complaint ORM model.

Stores the Anexo 1-A 15-field payload plus server-assigned bookkeeping
columns (``received_at``, ``etag_version``). The embedding column is
deliberately absent — ADR 0028 defers the embedding schema to Prompt 11
when the model family is chosen.
"""

from __future__ import annotations

from datetime import date, datetime

from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class ComplaintRecord(Base):
    __tablename__ = "complaints"

    complaint_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    institution_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("institutions.institution_id"), nullable=False
    )
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    complainant_doc_type: Mapped[str] = mapped_column(String(16), nullable=False)
    product_category: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    motivo_code: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    description_text: Mapped[str] = mapped_column(Text, nullable=False)
    description_language: Mapped[str] = mapped_column(String(8), nullable=False)
    complainant_age_range: Mapped[str] = mapped_column(String(16), nullable=False)
    complainant_district: Mapped[str] = mapped_column(String(6), nullable=False)
    submission_method: Mapped[str] = mapped_column(String(32), nullable=False)
    original_reference_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolution_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pendiente")
    # Tier provenance — `api_realtime` (Tier 1 POST) or `batch` (Tier 2 worker).
    # ADR 0034: same Pydantic validation for both tiers; the column records
    # which path a complaint travelled so dashboards can break out the mix.
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="api_realtime"
    )

    # Server-assigned bookkeeping.
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    # Optimistic-concurrency token. Increments on every mutation; the ETag
    # header is derived from this.
    etag_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Optional client-supplied correlation id, persisted for audit and for
    # the ComplaintCreated.client_submission_id echo.
    client_submission_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # P11 demo-ready overlay (migration 20260526_0001): the five
    # resolution-side Annex 1-A columns the real SBS sample exercises.
    # All nullable so historical rows remain valid and the migration is
    # reversible. The orchestrator populates them when the demo or
    # sandbox endpoint receives the corresponding fields.
    fecha_resolucion: Mapped[date | None] = mapped_column(Date, nullable=True)
    tipo_resolucion: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Redacted resolution narrative — never raw text.
    descripcion_resolucion: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Normalized state — ``atendido`` / ``en_proceso`` / ``pendiente``.
    estado_reclamo: Mapped[str | None] = mapped_column(String(32), nullable=True)
    monto_pendiente: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    __table_args__ = (
        Index(
            "ix_complaints_institution_received_at",
            "institution_id",
            "received_at",
        ),
        Index("ix_complaints_resolution_status", "resolution_status"),
        Index("ix_complaints_motivo_code", "motivo_code"),
        Index("ix_complaints_source", "source"),
    )
