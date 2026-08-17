# SPDX-License-Identifier: Apache-2.0
"""P11 demo-ui-polish overlay — flag_unknown_taxonomy on complaints.

Revision ID: 20260527_0001
Revises: 20260526_0001
Create Date: 2026-05-27

The demo-ready overlay landed taxonomy normalization on the ingestion
path and exposed ``flag_unknown_taxonomy`` on the SSE / agent_run
envelopes. The supervisor cockpit needs the flag on the canonical
``complaints`` row too so:

* Cockpit list rows can render a yellow left border + "Unknown term"
  pill + tooltip without joining audit_events on every read.
* A cockpit toolbar checkbox "Show only unknown taxonomy rows" can
  filter on a single indexed column.

Additive, nullable, defaults to false so existing rows backfill
correctly and the migration is reversible.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260527_0001"
down_revision: str | None = "20260526_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "complaints",
        sa.Column(
            "flag_unknown_taxonomy",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_complaints_flag_unknown_taxonomy",
        "complaints",
        ["flag_unknown_taxonomy"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_complaints_flag_unknown_taxonomy",
        table_name="complaints",
    )
    op.drop_column("complaints", "flag_unknown_taxonomy")
