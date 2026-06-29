# SPDX-License-Identifier: Apache-2.0
"""Raw-complaint ORM model — restricted PII-bearing storage for P11A.

This table is the **only** place the demo ingestion path persists raw
PII (full names, DNI numbers, phone numbers, email, account numbers,
free-text narrative as the caller sent it). Canonical complaints,
agent runs, audit events, and any SSE/UI surface receive redacted
text only.

Read access is restricted to the demo endpoint and explicit operator
queries. No cockpit / findings / audit / approvals builder imports
this model — that invariant is asserted by
``tests/integration/test_no_raw_pii_egress.py``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class RawComplaint(Base):
    __tablename__ = "raw_complaints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Null until the canonical complaint row is persisted. The demo
    # endpoint writes raw_complaints first, then complaints, then
    # backfills this FK.
    canonical_complaint_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("complaints.complaint_id"),
        nullable=True,
    )

    institution_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("institutions.institution_id"), nullable=False
    )

    client_submission_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    # JSON of the request body the demo endpoint received, verbatim.
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # The narrative as the caller sent it, before redaction.
    raw_narrative: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional response_detail (Anexo 1-A DET_RES) — also pre-redaction.
    # ``raw_response_detail`` is the legacy column name; the P11
    # demo-ready overlay added the canonical-aligned ``raw_descripcion_resolucion``
    # alongside it. The orchestrator writes both during the transition.
    raw_response_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_descripcion_resolucion: Mapped[str | None] = mapped_column(Text, nullable=True)

    storage_policy: Mapped[str] = mapped_column(
        String(64), nullable=False, default="restricted-demo-pii-v1"
    )

    # The redaction policy applied when producing the matching canonical
    # row. Stored here so a future re-redaction can be compared.
    redaction_policy_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_raw_complaints_institution_created_at",
            "institution_id",
            "created_at",
        ),
        Index(
            "ix_raw_complaints_canonical_complaint_id",
            "canonical_complaint_id",
        ),
    )
