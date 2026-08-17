# SPDX-License-Identifier: Apache-2.0
"""Social signal ORM models — the third cross-source feed (P-RESHAPE-6).

``social_signals`` is the live table the ingestion adapters write to.
``social_signals_fixture`` mirrors its schema exactly and holds the
seeded demo campaign; ``FixtureSocialAdapter`` reads from it. Splitting
the two keeps demo fixtures out of the live table while letting the
adapter interface stay production-shaped.

PII contract: ``post_text_es`` is stored ALREADY anonymized. User
handles are stripped at ingestion (``/@\\w+/`` → ``[HANDLE]``) and raw
user ids are never persisted. ``raw_url`` is audit-only and is never
surfaced to non-Analyst personas.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from sbs_api.db.base import Base

SOCIAL_SOURCES = ("TWITTER", "META", "REDDIT", "FIXTURE")

FRAUD_INDICATORS = (
    "PHISHING_KEYWORD",
    "SCAM_KEYWORD",
    "FAKE_APP_KEYWORD",
    "FAKE_AGENT_KEYWORD",
    "UNAUTHORIZED_FEE_KEYWORD",
    "UNAUTHORIZED_CHARGE_KEYWORD",
)


class _SocialSignalColumns:
    """Shared column set for the live + fixture tables (identical schema)."""

    signal_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    source_post_id: Mapped[str] = mapped_column(String(128), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    post_authored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    post_text_es: Mapped[str] = mapped_column(Text, nullable=False)
    detected_institution_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)), nullable=False
    )
    detected_fraud_indicators: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), nullable=False
    )
    engagement_score: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 3), nullable=True
    )
    raw_url: Mapped[str | None] = mapped_column(String(512), nullable=True)


class SocialSignal(_SocialSignalColumns, Base):
    __tablename__ = "social_signals"

    __table_args__ = (
        CheckConstraint(
            "source IN ('TWITTER','META','REDDIT','FIXTURE')",
            name="ck_social_signals_source",
        ),
        Index(
            "ix_social_signals_captured",
            "captured_at",
        ),
        Index(
            "ix_social_signals_source_post",
            "source",
            "source_post_id",
            unique=True,
        ),
    )


class SocialSignalFixture(_SocialSignalColumns, Base):
    __tablename__ = "social_signals_fixture"

    __table_args__ = (
        CheckConstraint(
            "source IN ('TWITTER','META','REDDIT','FIXTURE')",
            name="ck_social_signals_fixture_source",
        ),
    )
