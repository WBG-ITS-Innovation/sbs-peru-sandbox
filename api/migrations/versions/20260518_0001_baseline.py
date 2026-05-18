"""baseline — institutions, complaints, batches, idempotency_records

Revision ID: 20260518_0001
Revises:
Create Date: 2026-05-18

Schema matches the SQLAlchemy ORM models in :mod:`sbs_api.db.models`. The
embedding column is **not** included; the embedding storage decision is
deferred to Prompt 11 per ADR 0028.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260518_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The pgvector extension is created by the Postgres init script
    # (scripts/postgres-init.sql) for the Compose path; on production this
    # belongs to the DBA's pre-install checklist. The migration guards with
    # IF NOT EXISTS so re-runs are safe.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "institutions",
        sa.Column("institution_id", sa.String(length=10), primary_key=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("onboarded", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "rate_limit_per_minute", sa.Integer(), nullable=False, server_default="60"
        ),
        sa.Column(
            "schema_version", sa.String(length=16), nullable=False, server_default="v0.1.0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "complaints",
        sa.Column("complaint_id", sa.String(length=32), primary_key=True),
        sa.Column(
            "institution_id",
            sa.String(length=10),
            sa.ForeignKey("institutions.institution_id"),
            nullable=False,
        ),
        sa.Column("received_date", sa.Date(), nullable=False),
        sa.Column("complainant_doc_type", sa.String(length=16), nullable=False),
        sa.Column("product_category", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("motivo_code", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("description_text", sa.Text(), nullable=False),
        sa.Column("description_language", sa.String(length=8), nullable=False),
        sa.Column("complainant_age_range", sa.String(length=16), nullable=False),
        sa.Column("complainant_district", sa.String(length=6), nullable=False),
        sa.Column("submission_method", sa.String(length=32), nullable=False),
        sa.Column("original_reference_id", sa.String(length=32), nullable=True),
        sa.Column(
            "resolution_status",
            sa.String(length=16),
            nullable=False,
            server_default="pendiente",
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("etag_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("client_submission_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_complaints_institution_received_at",
        "complaints",
        ["institution_id", "received_at"],
    )
    op.create_index(
        "ix_complaints_resolution_status", "complaints", ["resolution_status"]
    )
    op.create_index("ix_complaints_motivo_code", "complaints", ["motivo_code"])

    op.create_table(
        "batches",
        sa.Column("batch_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "institution_id",
            sa.String(length=10),
            sa.ForeignKey("institutions.institution_id"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("reporting_period_start", sa.Date(), nullable=False),
        sa.Column("reporting_period_end", sa.Date(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("row_count_submitted", sa.Integer(), nullable=False),
        sa.Column(
            "row_count_accepted", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "row_count_rejected", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending_upload",
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_batches_institution_submitted_at",
        "batches",
        ["institution_id", "submitted_at"],
    )

    op.create_table(
        "idempotency_records",
        sa.Column("record_id", sa.String(length=32), primary_key=True),
        sa.Column("institution_id", sa.String(length=10), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("body_sha256", sa.LargeBinary(length=32), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_payload", sa.Text(), nullable=False),
        sa.Column(
            "response_headers", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column("request_method", sa.String(length=8), nullable=False),
        sa.Column("request_path", sa.String(length=256), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_idem_institution_key",
        "idempotency_records",
        ["institution_id", "idempotency_key"],
        unique=True,
    )
    op.create_index("ix_idem_expires_at", "idempotency_records", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_idem_expires_at", table_name="idempotency_records")
    op.drop_index("uq_idem_institution_key", table_name="idempotency_records")
    op.drop_table("idempotency_records")
    op.drop_index("ix_batches_institution_submitted_at", table_name="batches")
    op.drop_table("batches")
    op.drop_index("ix_complaints_motivo_code", table_name="complaints")
    op.drop_index("ix_complaints_resolution_status", table_name="complaints")
    op.drop_index("ix_complaints_institution_received_at", table_name="complaints")
    op.drop_table("complaints")
    op.drop_table("institutions")
    # The vector extension is left in place on downgrade — it may be in use by
    # other databases on the same cluster.
