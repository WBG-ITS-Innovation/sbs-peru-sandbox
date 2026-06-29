# SPDX-License-Identifier: Apache-2.0
"""P-RESHAPE-2 — pattern_detections + indecopi_cases tables.

Revision ID: 20260528_0001
Revises: 20260527_0001_agents_status
Create Date: 2026-05-28

Adds the aggregation layer's storage:

* ``indecopi_cases`` — small reference table the aggregation job joins
  against for the CROSS_SOURCE_CORRELATION rule. Seeded for the demo
  scenario; real INDECOPI feed ingestion is out of scope.
* ``pattern_detections`` — one row per (rule, bucket, window) the
  aggregation tick emitted. ``triggered_investigation`` and
  ``investigation_run_id`` close the loop with the Investigation
  orchestrator.

Both tables are additive — no existing column changes. Downgrade
drops them. Indices follow the access patterns the cockpit and the
orchestrator need (lookup by institution+category+detected_at for the
cockpit; lookup by band+triggered for the orchestrator's poll loop).
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260528_0001"
down_revision: str | None = "20260527_0001_agents_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "indecopi_cases",
        sa.Column("case_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "institution_id",
            sa.String(length=10),
            sa.ForeignKey("institutions.institution_id"),
            nullable=False,
        ),
        sa.Column("complaint_category", sa.String(length=64), nullable=False),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("summary", sa.String(length=512), nullable=True),
    )
    op.create_index(
        "ix_indecopi_cases_institution_category_opened",
        "indecopi_cases",
        ["institution_id", "complaint_category", "opened_at"],
    )

    op.create_table(
        "pattern_detections",
        sa.Column("pattern_id", sa.String(length=36), primary_key=True),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "window_start",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "window_end",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("institution_code", sa.String(length=16), nullable=False),
        sa.Column("complaint_category", sa.String(length=64), nullable=False),
        sa.Column("pattern_type", sa.String(length=32), nullable=False),
        sa.Column("severity_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("severity_band", sa.String(length=8), nullable=False),
        sa.Column(
            "contributing_complaint_ids",
            postgresql.ARRAY(sa.String(length=32)),
            nullable=False,
        ),
        sa.Column(
            "contributing_indecopi_case_ids",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=True,
        ),
        sa.Column(
            "composite_breakdown",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "triggered_investigation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "investigation_run_id",
            sa.String(length=64),
            nullable=True,
        ),
        sa.CheckConstraint(
            "pattern_type IN ('VOLUME_SPIKE','SUSTAINED_ELEVATION',"
            "'CROSS_SOURCE_CORRELATION','NEW_TOPIC_EMERGENCE')",
            name="ck_pattern_detections_pattern_type",
        ),
        sa.CheckConstraint(
            "severity_band IN ('HIGH','MEDIUM','LOW')",
            name="ck_pattern_detections_severity_band",
        ),
    )
    op.create_index(
        "ix_pattern_detections_inst_cat_detected",
        "pattern_detections",
        ["institution_code", "complaint_category", "detected_at"],
    )
    op.create_index(
        "ix_pattern_detections_band_triggered",
        "pattern_detections",
        ["severity_band", "triggered_investigation"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pattern_detections_band_triggered", table_name="pattern_detections"
    )
    op.drop_index(
        "ix_pattern_detections_inst_cat_detected", table_name="pattern_detections"
    )
    op.drop_table("pattern_detections")
    op.drop_index(
        "ix_indecopi_cases_institution_category_opened",
        table_name="indecopi_cases",
    )
    op.drop_table("indecopi_cases")
