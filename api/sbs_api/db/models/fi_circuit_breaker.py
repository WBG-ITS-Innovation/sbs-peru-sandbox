# SPDX-License-Identifier: Apache-2.0
"""FiCircuitBreaker — per-institution ingestion kill switch (P-RESHAPE-9).

SBS IT (ITOps) can PAUSE ingestion for one institution during a serious
incident. The ingestion pipeline reads this on every request and rejects
with 503 ``fi_circuit_breaker_paused`` while PAUSED. RESUME returns the
institution to NORMAL. High-privilege, so the action carries a 50-char
rationale and is audited.

One row per institution; absence of a row means NORMAL.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base

CIRCUIT_STATES = ("PAUSED", "NORMAL")


class FiCircuitBreaker(Base):
    __tablename__ = "fi_circuit_breakers"

    institution_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    state: Mapped[str] = mapped_column(String(8), nullable=False)
    set_by_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    set_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "state IN ('PAUSED','NORMAL')", name="ck_fi_circuit_breakers_state"
        ),
    )
