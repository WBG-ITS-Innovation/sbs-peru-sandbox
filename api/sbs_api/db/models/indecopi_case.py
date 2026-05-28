"""INDECOPI case ORM model.

INDECOPI (Instituto Nacional de Defensa de la Competencia y de la
Protección de la Propiedad Intelectual) is Peru's consumer-protection
authority. The aggregation job's CROSS_SOURCE_CORRELATION rule joins
complaints against open INDECOPI cases on the same
(institution, complaint_category) bucket: a same-week jump in
complaints that is *also* corroborated by an INDECOPI uptick is a
meaningfully stronger signal than complaints alone.

P-RESHAPE-2 adds the table; the data is seeded for the demo. Real-FI
ingestion of INDECOPI feeds is out of scope here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from sbs_api.db.base import Base


class IndecopiCase(Base):
    __tablename__ = "indecopi_cases"

    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("institutions.institution_id"),
        nullable=False,
    )
    complaint_category: Mapped[str] = mapped_column(String(64), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Free-text label for the cockpit drilldown. Not used by the
    # detector itself.
    summary: Mapped[str | None] = mapped_column(String(512), nullable=True)

    __table_args__ = (
        Index(
            "ix_indecopi_cases_institution_category_opened",
            "institution_id",
            "complaint_category",
            "opened_at",
        ),
    )
