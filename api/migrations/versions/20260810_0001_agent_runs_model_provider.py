# SPDX-License-Identifier: Apache-2.0
"""Record which provider actually served each agent run.

Revision ID: 20260810_0001
Revises: 20260529_0002
Create Date: 2026-08-10

``agent_runs`` captured the model_id but never the provider, so a run served
by MockProvider was indistinguishable in the database from one served by a
real vLLM endpoint. That gap matters because ``OnPremProvider`` falls back to
``MockProvider`` whenever no vLLM endpoint answers, logging the substitution
to stderr only — leaving ADR 0001's "every reasoning step is reconstructable
from the database without re-running the model" unsatisfiable for exactly the
runs where it matters most.

Additive and reversible: one nullable column, no backfill. Existing rows keep
NULL, which reads correctly as "provider not recorded" rather than asserting a
provider that was never captured.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0001"
down_revision: str | None = "20260529_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("model_provider", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "model_provider")
