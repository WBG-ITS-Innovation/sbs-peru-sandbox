"""P-RESHAPE-8 — DIValeVale validation tables.

Revision ID: 20260528_0007
Revises: 20260528_0006
Create Date: 2026-05-28

validation_audit + validation_batches + enrichment_requests. Additive.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260528_0007"
down_revision: str | None = "20260528_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "validation_audit",
        sa.Column("audit_id", sa.String(length=36), primary_key=True),
        sa.Column("complaint_id", sa.String(length=32), nullable=True),
        sa.Column("institution_code", sa.String(length=32), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column(
            "pass1_failed_rules",
            postgresql.ARRAY(sa.String(length=48)),
            nullable=False,
        ),
        sa.Column(
            "pass2_invoked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "pass2_recoveries",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("pass2_model_id", sa.String(length=96), nullable=True),
        sa.Column("routing_action", sa.String(length=32), nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=True),
        sa.Column("model_id", sa.String(length=96), nullable=False),
        sa.Column("model_provider", sa.String(length=16), nullable=False),
        sa.Column("tier", sa.String(length=8), nullable=False),
        sa.Column(
            "latency_ms", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.CheckConstraint(
            "verdict IN ('VALID','RECOVERABLE','INSUFFICIENT','INVALID')",
            name="ck_validation_audit_verdict",
        ),
        sa.CheckConstraint(
            "routing_action IN ('PROCEEDED_TO_TRIAGE','QUARANTINED_BATCH',"
            "'FLAGGED_FOR_ENRICHMENT','REJECTED')",
            name="ck_validation_audit_routing",
        ),
        sa.CheckConstraint(
            "tier IN ('TIER_1','TIER_2')", name="ck_validation_audit_tier"
        ),
    )
    op.create_index(
        "ix_validation_audit_institution_received",
        "validation_audit",
        ["institution_code", "received_at"],
    )
    op.create_index(
        "ix_validation_audit_verdict_received",
        "validation_audit",
        ["verdict", "received_at"],
    )
    op.create_index("ix_validation_audit_batch", "validation_audit", ["batch_id"])

    op.create_table(
        "validation_batches",
        sa.Column("batch_id", sa.String(length=64), primary_key=True),
        sa.Column("institution_code", sa.String(length=32), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("valid_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("recoverable_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("insufficient_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("invalid_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column(
            "diagnostic_report",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("replaced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_batch_id", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "state IN ('PROCESSING','QUARANTINED','ACCEPTED','REPLACED')",
            name="ck_validation_batches_state",
        ),
    )
    op.create_index(
        "ix_validation_batches_institution",
        "validation_batches",
        ["institution_code", "received_at"],
    )

    op.create_table(
        "enrichment_requests",
        sa.Column("request_id", sa.String(length=36), primary_key=True),
        sa.Column("complaint_id", sa.String(length=32), nullable=False),
        sa.Column("institution_code", sa.String(length=32), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "missing_fields",
            postgresql.ARRAY(sa.String(length=48)),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fulfilled_via_complaint_version", sa.String(length=64), nullable=True
        ),
        sa.Column("delivery_status", sa.String(length=16), nullable=False),
        sa.Column(
            "delivery_attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.CheckConstraint(
            "state IN ('PENDING','FULFILLED','EXPIRED','ESCALATED')",
            name="ck_enrichment_requests_state",
        ),
    )
    op.create_index(
        "ix_enrichment_requests_complaint", "enrichment_requests", ["complaint_id"]
    )
    op.create_index(
        "ix_enrichment_requests_state", "enrichment_requests", ["state", "deadline"]
    )


def downgrade() -> None:
    op.drop_index("ix_enrichment_requests_state", table_name="enrichment_requests")
    op.drop_index("ix_enrichment_requests_complaint", table_name="enrichment_requests")
    op.drop_table("enrichment_requests")
    op.drop_index("ix_validation_batches_institution", table_name="validation_batches")
    op.drop_table("validation_batches")
    op.drop_index("ix_validation_audit_batch", table_name="validation_audit")
    op.drop_index("ix_validation_audit_verdict_received", table_name="validation_audit")
    op.drop_index(
        "ix_validation_audit_institution_received", table_name="validation_audit"
    )
    op.drop_table("validation_audit")
