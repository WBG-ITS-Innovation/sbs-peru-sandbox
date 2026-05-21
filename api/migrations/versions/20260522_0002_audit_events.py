"""audit_events — cross-screen audit chain

Revision ID: 20260522_0002
Revises: 20260522_0001
Create Date: 2026-05-22

Prompt 10 / WS2. Lands the substrate the persona switcher (WS2),
approvals (WS5), and the audit screen (WS6) all read from and write to.
A single table, a single writer (``sbs_api.audit.record_audit_event``);
the audit screen will show every action because every screen routes
through that one entrypoint. Shape is intentionally string-y on
``action``, ``object_type``, ``object_id`` because new workstreams add
new vocabulary without a schema change.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260522_0002"
down_revision: str | None = "20260522_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("actor_type", sa.String(length=8), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("object_type", sa.String(length=32), nullable=False),
        sa.Column("object_id", sa.String(length=64), nullable=False),
        sa.Column(
            "diff",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.CheckConstraint(
            "actor_type IN ('user', 'agent')",
            name="ck_audit_events_actor_type",
        ),
        sa.CheckConstraint(
            "action ~ '^[a-z][a-z0-9-]*[a-z0-9]$'",
            name="ck_audit_events_action_kebab",
        ),
    )

    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index(
        "ix_audit_events_actor",
        "audit_events",
        ["actor_type", "actor_id", "created_at"],
    )
    op.create_index(
        "ix_audit_events_object",
        "audit_events",
        ["object_type", "object_id", "created_at"],
    )
    op.create_index("ix_audit_events_action", "audit_events", ["action"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_index("ix_audit_events_object", table_name="audit_events")
    op.drop_index("ix_audit_events_actor", table_name="audit_events")
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_table("audit_events")
