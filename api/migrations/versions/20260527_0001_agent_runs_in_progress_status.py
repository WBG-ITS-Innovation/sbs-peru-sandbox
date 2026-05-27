"""agent_runs.status: additive extension — add 'in_progress'.

Revision ID: 20260527_0001_agents_status
Revises: 20260527_0001
Create Date: 2026-05-27

Part 12 (Agent Layer) introduces in-flight agent rows. The original
constraint allowed only terminal states {success, partial, failed,
timeout}. This migration extends the set additively with
'in_progress'; no existing row needs to be rewritten and no caller
is renamed.
"""

from __future__ import annotations

from typing import Sequence

from alembic import op

revision: str = "20260527_0001_agents_status"
down_revision: str | None = "20260527_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_agent_runs_status", "agent_runs", type_="check")
    op.create_check_constraint(
        "ck_agent_runs_status",
        "agent_runs",
        "status IN ('in_progress', 'success', 'partial', 'failed', 'timeout')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM agent_runs WHERE status = 'in_progress'")
    op.drop_constraint("ck_agent_runs_status", "agent_runs", type_="check")
    op.create_check_constraint(
        "ck_agent_runs_status",
        "agent_runs",
        "status IN ('success', 'partial', 'failed', 'timeout')",
    )
