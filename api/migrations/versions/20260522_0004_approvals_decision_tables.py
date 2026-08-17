# SPDX-License-Identifier: Apache-2.0
"""supervisory_observations + agent_feedback — WS5 substrate

Revision ID: 20260522_0004
Revises: 20260522_0003
Create Date: 2026-05-22

Prompt 10 / WS5. Two tables the Approvals decision endpoints write to.

* ``supervisory_observations`` — the official record Approve and
  Approve-with-edits create. The head's final narrative lands here;
  the row is paired with the originating ``pending_approvals.id``.
* ``agent_feedback`` — what the model learns from human correction.
  Reject and Approve-with-edits both write rows. The 20-character
  rationale minimum is enforced at the DB level so a bypass cannot
  write a reject without explanation.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260522_0004"
down_revision: str | None = "20260522_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "supervisory_observations",
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
            "pending_approval_id",
            sa.BigInteger(),
            sa.ForeignKey("pending_approvals.id"),
            nullable=False,
        ),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.String(length=128), nullable=False),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("agent_version", sa.String(length=96), nullable=True),
        sa.Column(
            "model_versions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_supervisory_observations_complaint_approved",
        "supervisory_observations",
        ["complaint_id", "approved_at"],
    )
    op.create_index(
        "ix_supervisory_observations_pending_approval",
        "supervisory_observations",
        ["pending_approval_id"],
    )

    op.create_table(
        "agent_feedback",
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
            "pending_approval_id",
            sa.BigInteger(),
            sa.ForeignKey("pending_approvals.id"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column(
            "edit_diff",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("recorded_by", sa.String(length=128), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "decision IN ('reject', 'approve-with-edits')",
            name="ck_agent_feedback_decision",
        ),
        sa.CheckConstraint(
            "char_length(rationale) >= 20",
            name="ck_agent_feedback_rationale_min_length",
        ),
    )
    op.create_index(
        "ix_agent_feedback_complaint_recorded",
        "agent_feedback",
        ["complaint_id", "recorded_at"],
    )
    op.create_index(
        "ix_agent_feedback_pending_approval",
        "agent_feedback",
        ["pending_approval_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_feedback_pending_approval", table_name="agent_feedback")
    op.drop_index("ix_agent_feedback_complaint_recorded", table_name="agent_feedback")
    op.drop_table("agent_feedback")
    op.drop_index(
        "ix_supervisory_observations_pending_approval",
        table_name="supervisory_observations",
    )
    op.drop_index(
        "ix_supervisory_observations_complaint_approved",
        table_name="supervisory_observations",
    )
    op.drop_table("supervisory_observations")
