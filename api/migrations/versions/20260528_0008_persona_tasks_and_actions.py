# SPDX-License-Identifier: Apache-2.0
"""P-RESHAPE-8.5 — persona task inbox + action-surface tables.

Revision ID: 20260528_0008
Revises: 20260528_0007
Create Date: 2026-05-28

Additive. Four tables: persona_tasks (inbox/outbox), manual_findings
(analyst pattern proposals), digest_audit (weekly exec digest lifecycle),
incident_annotations (SBS IT operational notes).
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260528_0008"
down_revision: str | None = "20260528_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "persona_tasks",
        sa.Column("task_id", sa.String(length=36), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("created_by_user_id", sa.String(length=128), nullable=False),
        sa.Column("created_by_persona", sa.String(length=48), nullable=False),
        sa.Column("assigned_to_user_id", sa.String(length=128), nullable=True),
        sa.Column("assigned_to_persona", sa.String(length=48), nullable=False),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("ref_type", sa.String(length=32), nullable=False),
        sa.Column("ref_id", sa.String(length=64), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column(
            "state",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'OPEN'"),
        ),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "task_type IN ('DEEPER_LOOK','PATTERN_DELEGATION',"
            "'ENRICHMENT_REQUEST','FI_BRIEF_REVIEW','DIGEST_ACK')",
            name="ck_persona_tasks_task_type",
        ),
        sa.CheckConstraint(
            "state IN ('OPEN','ACKED','COMPLETED','DECLINED')",
            name="ck_persona_tasks_state",
        ),
    )
    op.create_index(
        "ix_persona_tasks_assignee_state",
        "persona_tasks",
        ["assigned_to_user_id", "state"],
    )
    op.create_index(
        "ix_persona_tasks_persona_state",
        "persona_tasks",
        ["assigned_to_persona", "state"],
    )
    op.create_index(
        "ix_persona_tasks_creator_created",
        "persona_tasks",
        ["created_by_user_id", "created_at"],
    )

    op.create_table(
        "manual_findings",
        sa.Column("finding_id", sa.String(length=36), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("proposed_by_user_id", sa.String(length=128), nullable=False),
        sa.Column("persona", sa.String(length=48), nullable=False),
        sa.Column("institution_code", sa.String(length=32), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'PROPOSED'"),
        ),
    )
    op.create_index("ix_manual_findings_created", "manual_findings", ["created_at"])

    op.create_table(
        "digest_audit",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("digest_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("actor_user_id", sa.String(length=128), nullable=False),
        sa.Column("persona", sa.String(length=48), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('GENERATED','ACKNOWLEDGED')",
            name="ck_digest_audit_event_type",
        ),
    )
    op.create_index(
        "ix_digest_audit_digest", "digest_audit", ["digest_id", "occurred_at"]
    )

    op.create_table(
        "incident_annotations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("actor_user_id", sa.String(length=128), nullable=False),
        sa.Column("component", sa.String(length=64), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_incident_annotations_created", "incident_annotations", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_incident_annotations_created", table_name="incident_annotations"
    )
    op.drop_table("incident_annotations")
    op.drop_index("ix_digest_audit_digest", table_name="digest_audit")
    op.drop_table("digest_audit")
    op.drop_index("ix_manual_findings_created", table_name="manual_findings")
    op.drop_table("manual_findings")
    op.drop_index("ix_persona_tasks_creator_created", table_name="persona_tasks")
    op.drop_index("ix_persona_tasks_persona_state", table_name="persona_tasks")
    op.drop_index("ix_persona_tasks_assignee_state", table_name="persona_tasks")
    op.drop_table("persona_tasks")
