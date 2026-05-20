"""tier 2 batch — file_path on batches, complaints.source, rejections, webhook tables

Revision ID: 20260520_0001
Revises: 20260519_0003
Create Date: 2026-05-20

Prompt 8 / Part 4 — the Tier 2 batch ingestion path lands here. Adds:

* ``complaints.source`` provenance column (`api_realtime` | `batch`). Pre-
  existing complaint rows are backfilled to ``api_realtime``; the Tier 1
  POST handler writes ``api_realtime``; the Tier 2 worker writes ``batch``.
* ``batches.file_path`` and ``batches.failure_reason`` so the new endpoint
  can record where the CSV was persisted and why a batch failed.
* ``batch_row_rejections`` — per-row failure detail. Populated by the arq
  worker per ADR 0034.
* ``institution_webhook_configs`` — per-institution callback URL (one URL,
  one row). ``event_type`` deliberately omitted (YAGNI; revisit in Prompt 12).
* ``outbound_webhook_secrets`` — per-institution outbound HMAC secret with a
  ``kid`` column so future rotation can hold an active and a previous secret
  keyed by kid. Mirrors institution_secrets shape.
* ``webhook_deliveries`` — one row per outbound callback attempt window. The
  delivery worker (Workstream D) reads this for retry scheduling and writes
  ``attempt_history`` JSON for observability.

OAuth-client cert-thumbprint seeding (closes the Prompt 7 Day-2 deferral)
lives in ``scripts/seed-oauth-clients.sh`` instead of this migration: at
migration time the ``institution_certificates`` rows have not yet been
loaded (dev-up.sh runs alembic before scripts/dev-ca.sh seeds certs), so
the migration cannot read the thumbprint to set. Doing the data update in
the seed script keeps the ordering coherent.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260520_0001"
down_revision: str | None = "20260519_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- complaints.source ----------------------------------------------
    op.add_column(
        "complaints",
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            server_default="api_realtime",
        ),
    )
    op.create_index("ix_complaints_source", "complaints", ["source"])

    # --- batches: file_path + failure_reason ----------------------------
    op.add_column(
        "batches",
        sa.Column("file_path", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "batches",
        sa.Column("failure_reason", sa.Text(), nullable=True),
    )

    # --- batch_row_rejections -------------------------------------------
    op.create_table(
        "batch_row_rejections",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "batch_id",
            sa.String(length=64),
            sa.ForeignKey("batches.batch_id"),
            nullable=False,
        ),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("field", sa.String(length=200), nullable=True),
        sa.Column("rule", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("raw_row_excerpt", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_batch_row_rejections_batch_id",
        "batch_row_rejections",
        ["batch_id"],
    )
    op.create_index(
        "ix_batch_row_rejections_batch_row",
        "batch_row_rejections",
        ["batch_id", "row_index"],
    )

    # --- institution_webhook_configs ------------------------------------
    op.create_table(
        "institution_webhook_configs",
        sa.Column(
            "institution_id",
            sa.String(length=10),
            sa.ForeignKey("institutions.institution_id"),
            primary_key=True,
        ),
        sa.Column("callback_url", sa.String(length=512), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # --- outbound_webhook_secrets ---------------------------------------
    op.create_table(
        "outbound_webhook_secrets",
        sa.Column(
            "institution_id",
            sa.String(length=10),
            sa.ForeignKey("institutions.institution_id"),
            primary_key=True,
        ),
        sa.Column(
            "kid",
            sa.String(length=32),
            nullable=False,
            server_default="sandbox-v1",
        ),
        sa.Column("active_secret", sa.LargeBinary(length=64), nullable=False),
        sa.Column("previous_secret", sa.LargeBinary(length=64), nullable=True),
        sa.Column(
            "previous_secret_retires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "rotated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # --- webhook_deliveries ---------------------------------------------
    op.create_table(
        "webhook_deliveries",
        sa.Column("delivery_id", sa.String(length=40), primary_key=True),
        sa.Column(
            "batch_id",
            sa.String(length=64),
            sa.ForeignKey("batches.batch_id"),
            nullable=False,
        ),
        sa.Column(
            "institution_id",
            sa.String(length=10),
            sa.ForeignKey("institutions.institution_id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "attempt_history",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_webhook_deliveries_batch_id",
        "webhook_deliveries",
        ["batch_id"],
    )
    op.create_index(
        "ix_webhook_deliveries_status_next_attempt",
        "webhook_deliveries",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_webhook_deliveries_status_next_attempt",
        table_name="webhook_deliveries",
    )
    op.drop_index(
        "ix_webhook_deliveries_batch_id",
        table_name="webhook_deliveries",
    )
    op.drop_table("webhook_deliveries")
    op.drop_table("outbound_webhook_secrets")
    op.drop_table("institution_webhook_configs")
    op.drop_index(
        "ix_batch_row_rejections_batch_row",
        table_name="batch_row_rejections",
    )
    op.drop_index(
        "ix_batch_row_rejections_batch_id",
        table_name="batch_row_rejections",
    )
    op.drop_table("batch_row_rejections")
    op.drop_column("batches", "failure_reason")
    op.drop_column("batches", "file_path")
    op.drop_index("ix_complaints_source", table_name="complaints")
    op.drop_column("complaints", "source")
