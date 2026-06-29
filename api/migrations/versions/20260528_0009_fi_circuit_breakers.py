# SPDX-License-Identifier: Apache-2.0
"""P-RESHAPE-9 — fi_circuit_breakers table.

Revision ID: 20260528_0009
Revises: 20260528_0008
Create Date: 2026-05-28

Per-institution ingestion kill switch for SBS IT remediation. Additive.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260528_0009"
down_revision: str | None = "20260528_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fi_circuit_breakers",
        sa.Column("institution_code", sa.String(length=32), primary_key=True),
        sa.Column("state", sa.String(length=8), nullable=False),
        sa.Column("set_by_user_id", sa.String(length=128), nullable=False),
        sa.Column(
            "set_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "state IN ('PAUSED','NORMAL')", name="ck_fi_circuit_breakers_state"
        ),
    )


def downgrade() -> None:
    op.drop_table("fi_circuit_breakers")
