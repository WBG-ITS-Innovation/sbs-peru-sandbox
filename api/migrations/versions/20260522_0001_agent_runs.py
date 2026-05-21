"""agent_runs — durable execution trace for the supervisor UI

Revision ID: 20260522_0001
Revises: 20260520_0001
Create Date: 2026-05-22

Prompt 10 / WS0b. Adds the ``agent_runs`` table that the supervisor UI's
Findings drilldown and Approvals evidence panel read from. The shape of
every row is governed by the JSON Schema contract at
``docs/schemas/agent_run.schema.json``; the narrative semantics live at
``docs/schemas/agent_run.md``.

This migration creates the storage layer only. The Prompt 10 WS0 seed
script populates rows with realistic agent traces (including the three
required partial-failure shapes: BERT timeout, XGBoost unavailable,
anonymizer error); Prompt 12 replaces seeded rows with live agent output.
The integration test ``tests/integration/test_agent_run_schema.py``
validates both seeded and live rows against the JSON Schema.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260522_0001"
down_revision: str | None = "20260520_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "complaint_id",
            sa.String(length=32),
            sa.ForeignKey("complaints.complaint_id"),
            nullable=False,
        ),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("agent_version", sa.String(length=96), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "ended_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "tool_calls",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "final_output",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "error",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.CheckConstraint(
            "status IN ('success', 'partial', 'failed', 'timeout')",
            name="ck_agent_runs_status",
        ),
    )

    op.create_index(
        "ix_agent_runs_complaint_id_started_at",
        "agent_runs",
        ["complaint_id", "started_at"],
    )
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index(
        "ix_agent_runs_agent_name_started_at",
        "agent_runs",
        ["agent_name", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_runs_agent_name_started_at", table_name="agent_runs")
    op.drop_index("ix_agent_runs_status", table_name="agent_runs")
    op.drop_index(
        "ix_agent_runs_complaint_id_started_at", table_name="agent_runs"
    )
    op.drop_table("agent_runs")
