"""P-RESHAPE-3 — peer_risk_analyses table.

Revision ID: 20260528_0002
Revises: 20260528_0001
Create Date: 2026-05-28

One row per (pattern_id, run) — pre-computed peer position, forecast,
and bilingual narrative for the cockpit drilldown. ``model_provider``
is constrained so the v1 "PRR is on-prem only" stance is enforced at
the storage layer; loosening it requires a follow-up migration and an
ADR amendment.

Foreign-key to ``pattern_detections.pattern_id`` couples the analysis
to its source pattern so cascade-on-delete makes the cockpit purge
behaviour predictable.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260528_0002"
down_revision: str | None = "20260528_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "peer_risk_analyses",
        sa.Column("analysis_id", sa.String(length=36), primary_key=True),
        sa.Column(
            "pattern_id",
            sa.String(length=36),
            sa.ForeignKey("pattern_detections.pattern_id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("cohort_id", sa.String(length=32), nullable=False),
        sa.Column("peer_count", sa.Integer(), nullable=False),
        sa.Column("percentile", sa.Numeric(5, 2), nullable=True),
        sa.Column("z_score", sa.Numeric(6, 3), nullable=True),
        sa.Column(
            "is_outlier",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "forecast",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("narrative_es", sa.Text(), nullable=False),
        sa.Column("narrative_en", sa.Text(), nullable=True),
        sa.Column("model_id", sa.String(length=96), nullable=False),
        sa.Column("model_provider", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "model_provider IN ('onprem','replay','mock','template')",
            name="ck_peer_risk_analyses_model_provider",
        ),
    )
    op.create_index(
        "ix_peer_risk_analyses_pattern_id",
        "peer_risk_analyses",
        ["pattern_id"],
    )
    op.create_index(
        "ix_peer_risk_analyses_cohort_created",
        "peer_risk_analyses",
        ["cohort_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_peer_risk_analyses_cohort_created", table_name="peer_risk_analyses"
    )
    op.drop_index(
        "ix_peer_risk_analyses_pattern_id", table_name="peer_risk_analyses"
    )
    op.drop_table("peer_risk_analyses")
