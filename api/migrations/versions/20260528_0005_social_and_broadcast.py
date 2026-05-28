"""P-RESHAPE-6 — social signals + fraud cross-source + sector broadcast.

Revision ID: 20260528_0005
Revises: 20260528_0004
Create Date: 2026-05-28

Adds:
* ``social_signals`` + ``social_signals_fixture`` — the third
  cross-source feed (ingestion writes the former; the fixture adapter
  reads the latter).
* ``fi_brand_aliases`` — handle/brand lookup for social entity
  resolution.
* ``sector_broadcasts`` + ``sector_broadcast_deliveries`` +
  ``sector_broadcast_audit`` — the sector-level fraud-warning surface
  with dual approval and per-recipient delivery tracking.

All additive.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260528_0005"
down_revision: str | None = "20260528_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _social_columns() -> list[sa.Column]:
    return [
        sa.Column("signal_id", sa.String(length=36), primary_key=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("source_post_id", sa.String(length=128), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("post_authored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("post_text_es", sa.Text(), nullable=False),
        sa.Column(
            "detected_institution_codes",
            postgresql.ARRAY(sa.String(length=16)),
            nullable=False,
        ),
        sa.Column(
            "detected_fraud_indicators",
            postgresql.ARRAY(sa.String(length=40)),
            nullable=False,
        ),
        sa.Column("engagement_score", sa.Numeric(8, 3), nullable=True),
        sa.Column("raw_url", sa.String(length=512), nullable=True),
    ]


def upgrade() -> None:
    # Extend the pattern_type check constraint (created in 20260528_0001)
    # to admit the new FRAUD_EMERGENCE type.
    op.drop_constraint(
        "ck_pattern_detections_pattern_type", "pattern_detections", type_="check"
    )
    op.create_check_constraint(
        "ck_pattern_detections_pattern_type",
        "pattern_detections",
        "pattern_type IN ('VOLUME_SPIKE','SUSTAINED_ELEVATION',"
        "'CROSS_SOURCE_CORRELATION','NEW_TOPIC_EMERGENCE','FRAUD_EMERGENCE')",
    )

    op.create_table(
        "social_signals",
        *_social_columns(),
        sa.CheckConstraint(
            "source IN ('TWITTER','META','REDDIT','FIXTURE')",
            name="ck_social_signals_source",
        ),
    )
    op.create_index("ix_social_signals_captured", "social_signals", ["captured_at"])
    op.create_index(
        "ix_social_signals_source_post",
        "social_signals",
        ["source", "source_post_id"],
        unique=True,
    )

    op.create_table(
        "social_signals_fixture",
        *_social_columns(),
        sa.CheckConstraint(
            "source IN ('TWITTER','META','REDDIT','FIXTURE')",
            name="ck_social_signals_fixture_source",
        ),
    )

    op.create_table(
        "fi_brand_aliases",
        sa.Column("alias_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "institution_id",
            sa.String(length=10),
            sa.ForeignKey("institutions.institution_id"),
            nullable=False,
        ),
        sa.Column("alias_normalized", sa.String(length=128), nullable=False),
        sa.Column("alias_kind", sa.String(length=16), nullable=False),
    )
    op.create_index(
        "ix_fi_brand_aliases_normalized", "fi_brand_aliases", ["alias_normalized"]
    )

    op.create_table(
        "sector_broadcasts",
        sa.Column("broadcast_id", sa.String(length=36), primary_key=True),
        sa.Column(
            "origin_pattern_id",
            sa.String(length=36),
            sa.ForeignKey("pattern_detections.pattern_id"),
            nullable=False,
        ),
        sa.Column(
            "origin_fi_anonymized",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "target_fi_codes",
            postgresql.ARRAY(sa.String(length=16)),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("threat_summary_es", sa.Text(), nullable=False),
        sa.Column("threat_summary_en", sa.Text(), nullable=True),
        sa.Column(
            "threat_indicators",
            postgresql.ARRAY(sa.String(length=40)),
            nullable=False,
        ),
        sa.Column(
            "suggested_controls",
            postgresql.ARRAY(sa.String(length=40)),
            nullable=False,
        ),
        sa.Column("urgency", sa.String(length=16), nullable=False),
        sa.Column("response_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "requires_dual_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("primary_approver", sa.String(length=128), nullable=True),
        sa.Column("primary_approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("primary_rationale", sa.Text(), nullable=True),
        sa.Column("secondary_approver", sa.String(length=128), nullable=True),
        sa.Column(
            "secondary_approved_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("secondary_rationale", sa.Text(), nullable=True),
        sa.Column("rejected_by", sa.String(length=128), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_id", sa.String(length=96), nullable=False),
        sa.Column("model_provider", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','AWAITING_DUAL_APPROVAL',"
            "'AWAITING_SECONDARY_APPROVAL','APPROVED','DELIVERING',"
            "'DELIVERED','PARTIALLY_DELIVERED','REJECTED')",
            name="ck_sector_broadcasts_status",
        ),
        sa.CheckConstraint(
            "urgency IN ('ROUTINE','ELEVATED','CRITICAL')",
            name="ck_sector_broadcasts_urgency",
        ),
    )
    op.create_index(
        "ix_sector_broadcasts_status_created",
        "sector_broadcasts",
        ["status", "created_at"],
    )

    op.create_table(
        "sector_broadcast_deliveries",
        sa.Column("delivery_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "broadcast_id",
            sa.String(length=36),
            sa.ForeignKey("sector_broadcasts.broadcast_id"),
            nullable=False,
        ),
        sa.Column("target_fi_code", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_sector_broadcast_deliveries_broadcast_target",
        "sector_broadcast_deliveries",
        ["broadcast_id", "target_fi_code"],
        unique=True,
    )

    op.create_table(
        "sector_broadcast_audit",
        sa.Column("event_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "broadcast_id",
            sa.String(length=36),
            sa.ForeignKey("sector_broadcasts.broadcast_id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_sector_broadcast_audit_broadcast_occurred",
        "sector_broadcast_audit",
        ["broadcast_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_pattern_detections_pattern_type", "pattern_detections", type_="check"
    )
    op.create_check_constraint(
        "ck_pattern_detections_pattern_type",
        "pattern_detections",
        "pattern_type IN ('VOLUME_SPIKE','SUSTAINED_ELEVATION',"
        "'CROSS_SOURCE_CORRELATION','NEW_TOPIC_EMERGENCE')",
    )
    op.drop_index(
        "ix_sector_broadcast_audit_broadcast_occurred",
        table_name="sector_broadcast_audit",
    )
    op.drop_table("sector_broadcast_audit")
    op.drop_index(
        "ix_sector_broadcast_deliveries_broadcast_target",
        table_name="sector_broadcast_deliveries",
    )
    op.drop_table("sector_broadcast_deliveries")
    op.drop_index(
        "ix_sector_broadcasts_status_created", table_name="sector_broadcasts"
    )
    op.drop_table("sector_broadcasts")
    op.drop_index("ix_fi_brand_aliases_normalized", table_name="fi_brand_aliases")
    op.drop_table("fi_brand_aliases")
    op.drop_table("social_signals_fixture")
    op.drop_index("ix_social_signals_source_post", table_name="social_signals")
    op.drop_index("ix_social_signals_captured", table_name="social_signals")
    op.drop_table("social_signals")
