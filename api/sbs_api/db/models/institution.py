"""Institution onboarding state.

Two demo institutions are pre-seeded in the test fixture and the
``scripts/dev-up.sh`` smoke test: ``BANCO_DEMO_001`` and ``COOPAC_DEMO_002``,
both with valid Anexo 1-A institution codes.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class InstitutionRecord(Base):
    __tablename__ = "institutions"

    institution_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    onboarded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v0.1.0")
    permitted_scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)),
        nullable=False,
        server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
