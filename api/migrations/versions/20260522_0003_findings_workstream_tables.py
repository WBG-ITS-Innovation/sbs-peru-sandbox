"""complaint_narrative_drafts + pending_approvals — WS4 substrate

Revision ID: 20260522_0003
Revises: 20260522_0002
Create Date: 2026-05-22

Prompt 10 / WS4. Two tables that the Findings drilldown writes to:

* ``complaint_narrative_drafts`` — append-only history of every
  the Conduct Analyst-edit of an agent-drafted narrative. The matching
  ``audit_events`` row (action='edit-draft-narrative') ties the edit
  to the operator. The latest row by ``created_at`` is the current
  draft.

* ``pending_approvals`` — the queue WS5 reads. A "Send to Approvals"
  button on Findings creates a row in status='pending'; WS5's decision
  endpoints (approve / approve-with-edits / reject / send-back) update
  the same row. Idempotency is application-level — see the route
  handler.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260522_0003"
down_revision: str | None = "20260522_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "complaint_narrative_drafts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "complaint_id",
            sa.String(length=32),
            sa.ForeignKey("complaints.complaint_id"),
            nullable=False,
        ),
        sa.Column(
            "agent_run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id"),
            nullable=True,
        ),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("before_text", sa.Text(), nullable=False),
        sa.Column("after_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_complaint_narrative_drafts_complaint_id_created_at",
        "complaint_narrative_drafts",
        ["complaint_id", "created_at"],
    )

    op.create_table(
        "pending_approvals",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "complaint_id",
            sa.String(length=32),
            sa.ForeignKey("complaints.complaint_id"),
            nullable=False,
        ),
        sa.Column(
            "agent_run_id",
            sa.String(length=36),
            sa.ForeignKey("agent_runs.id"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("decision_action", sa.String(length=32), nullable=True),
        sa.Column("decision_rationale", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'sent_back')",
            name="ck_pending_approvals_status",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_pending_approvals_severity",
        ),
    )
    op.create_index(
        "ix_pending_approvals_status_created_at",
        "pending_approvals",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_pending_approvals_complaint_id",
        "pending_approvals",
        ["complaint_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pending_approvals_complaint_id", table_name="pending_approvals"
    )
    op.drop_index(
        "ix_pending_approvals_status_created_at", table_name="pending_approvals"
    )
    op.drop_table("pending_approvals")

    op.drop_index(
        "ix_complaint_narrative_drafts_complaint_id_created_at",
        table_name="complaint_narrative_drafts",
    )
    op.drop_table("complaint_narrative_drafts")
