# SPDX-License-Identifier: Apache-2.0
"""raw_complaints — restricted PII-bearing storage for P11A demo ingestion

Revision ID: 20260524_0001
Revises: 20260522_0004
Create Date: 2026-05-24

P11A overlay. The demo ingestion path at
``POST /v1/internal/demo/simulate-submission`` accepts a realistic
Anexo-1A-shaped complaint, including PII fields the regulator should
never see in canonical storage. This migration adds a separate
``raw_complaints`` table that holds the raw payload + raw narrative
**only**. No code path outside the demo endpoint and explicit
operator queries reads this table. Canonical ``complaints``,
``agent_runs``, ``audit_events`` and any UI/SSE surface receive only
redacted text. See ADR 0044 (redaction) and ADR 0045 (data-quality).

The table is intentionally append-only and carries the redaction
policy version used at ingest time, so future audits can replay the
redaction with the same policy.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260524_0001"
down_revision: str | None = "20260522_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "raw_complaints",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "canonical_complaint_id",
            sa.String(length=32),
            sa.ForeignKey("complaints.complaint_id"),
            nullable=True,
        ),
        sa.Column(
            "institution_id",
            sa.String(length=10),
            sa.ForeignKey("institutions.institution_id"),
            nullable=False,
        ),
        sa.Column("client_submission_id", sa.String(length=64), nullable=True),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("raw_narrative", sa.Text(), nullable=False),
        sa.Column("raw_response_detail", sa.Text(), nullable=True),
        sa.Column(
            "storage_policy",
            sa.String(length=64),
            nullable=False,
            server_default="restricted-demo-pii-v1",
        ),
        sa.Column(
            "redaction_policy_version",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_raw_complaints_institution_created_at",
        "raw_complaints",
        ["institution_id", "created_at"],
    )
    op.create_index(
        "ix_raw_complaints_canonical_complaint_id",
        "raw_complaints",
        ["canonical_complaint_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_raw_complaints_canonical_complaint_id",
        table_name="raw_complaints",
    )
    op.drop_index(
        "ix_raw_complaints_institution_created_at",
        table_name="raw_complaints",
    )
    op.drop_table("raw_complaints")
