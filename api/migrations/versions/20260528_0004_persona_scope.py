"""P-RESHAPE-5 — persona_assignments + persona_audit tables.

Revision ID: 20260528_0004
Revises: 20260528_0003
Create Date: 2026-05-28

Storage for the persona-scoped cockpit: cross-persona handoffs
(``persona_assignments``) and the append-only persona-action log
(``persona_audit``). Both additive.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260528_0004"
down_revision: str | None = "20260528_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "persona_assignments",
        sa.Column(
            "assignment_id", sa.Integer(), primary_key=True, autoincrement=True
        ),
        sa.Column("source_user_id", sa.String(length=128), nullable=False),
        sa.Column("target_user_id", sa.String(length=128), nullable=False),
        sa.Column("target_persona", sa.String(length=32), nullable=False),
        sa.Column("ref_type", sa.String(length=16), nullable=False),
        sa.Column("ref_id", sa.String(length=64), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "ref_type IN ('PATTERN','COMPLAINT','FIBRIEF')",
            name="ck_persona_assignments_ref_type",
        ),
    )
    op.create_index(
        "ix_persona_assignments_target_ack",
        "persona_assignments",
        ["target_user_id", "acknowledged_at"],
    )

    op.create_table(
        "persona_audit",
        sa.Column("event_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_user_id", sa.String(length=128), nullable=False),
        sa.Column("persona", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_persona_audit_actor_occurred",
        "persona_audit",
        ["actor_user_id", "occurred_at"],
    )
    op.create_index(
        "ix_persona_audit_action_occurred",
        "persona_audit",
        ["action", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_persona_audit_action_occurred", table_name="persona_audit")
    op.drop_index("ix_persona_audit_actor_occurred", table_name="persona_audit")
    op.drop_table("persona_audit")
    op.drop_index(
        "ix_persona_assignments_target_ack", table_name="persona_assignments"
    )
    op.drop_table("persona_assignments")
