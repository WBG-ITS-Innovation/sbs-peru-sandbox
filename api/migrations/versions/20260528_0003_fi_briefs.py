"""P-RESHAPE-4 — fi_briefs + fi_brief_audit tables.

Revision ID: 20260528_0003
Revises: 20260528_0002
Create Date: 2026-05-28

Storage for the Issue Resurface agent's pre-escalation feedback brief
and its append-only audit log. Both additive. FKs to
``peer_risk_analyses`` and ``pattern_detections`` couple a brief to its
upstream analysis so cockpit purges cascade predictably.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260528_0003"
down_revision: str | None = "20260528_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fi_briefs",
        sa.Column("brief_id", sa.String(length=36), primary_key=True),
        sa.Column(
            "peer_risk_analysis_id",
            sa.String(length=36),
            sa.ForeignKey("peer_risk_analyses.analysis_id"),
            nullable=False,
        ),
        sa.Column(
            "pattern_id",
            sa.String(length=36),
            sa.ForeignKey("pattern_detections.pattern_id"),
            nullable=False,
        ),
        sa.Column("institution_id", sa.String(length=10), nullable=False),
        sa.Column("motivo_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("pattern_summary_es", sa.Text(), nullable=False),
        sa.Column("pattern_summary_en", sa.Text(), nullable=True),
        sa.Column("peer_context_es", sa.Text(), nullable=False),
        sa.Column("peer_context_en", sa.Text(), nullable=True),
        sa.Column(
            "suggested_remediation_areas",
            postgresql.ARRAY(sa.String(length=40)),
            nullable=False,
        ),
        sa.Column(
            "response_deadline",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("evidence_complaint_count", sa.Integer(), nullable=False),
        sa.Column(
            "evidence_window_start",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "evidence_window_end",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("approved_by", sa.String(length=128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_rationale", sa.Text(), nullable=True),
        sa.Column("rejected_by", sa.String(length=128), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ack_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ack_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "delivery_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("model_id", sa.String(length=96), nullable=False),
        sa.Column("model_provider", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','AWAITING_APPROVAL','APPROVED','REJECTED',"
            "'PENDING','SENT','DELIVERED','DELIVERY_FAILED','ACKED')",
            name="ck_fi_briefs_status",
        ),
    )
    op.create_index(
        "ix_fi_briefs_institution_motivo_created",
        "fi_briefs",
        ["institution_id", "motivo_code", "created_at"],
    )
    op.create_index(
        "ix_fi_briefs_status_created",
        "fi_briefs",
        ["status", "created_at"],
    )

    op.create_table(
        "fi_brief_audit",
        sa.Column("event_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "brief_id",
            sa.String(length=36),
            sa.ForeignKey("fi_briefs.brief_id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column(
            "event_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_fi_brief_audit_brief_id_occurred",
        "fi_brief_audit",
        ["brief_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fi_brief_audit_brief_id_occurred", table_name="fi_brief_audit"
    )
    op.drop_table("fi_brief_audit")
    op.drop_index("ix_fi_briefs_status_created", table_name="fi_briefs")
    op.drop_index(
        "ix_fi_briefs_institution_motivo_created", table_name="fi_briefs"
    )
    op.drop_table("fi_briefs")
