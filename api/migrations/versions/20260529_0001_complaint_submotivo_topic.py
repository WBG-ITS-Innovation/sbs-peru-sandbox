"""Aggregate-dashboard enrichment — add submotivo, submotivo_2, topic to complaints.

Revision ID: 20260529_0001
Revises: 20260528_0009
Create Date: 2026-05-29

The aggregate dashboard needs finer grouping dimensions than the single
``motivo_code``. This migration adds three nullable columns to
``complaints``:

* ``submotivo``    — finer motive level (e.g. COBRO_INDEBIDO →
                     "comisión de mantenimiento").
* ``submotivo_2``  — optional second level; NULL for many complaints.
* ``topic``        — trend / topic tag (e.g. "fallas app").

These are SYNTHETIC / DERIVED fields, not part of the institutional
Anexo 1-A submission contract. In production a BERT + regex classifier
populates them from the narrative; the synthetic corpus seeds them
deterministically. All three are nullable so existing rows backfill to
NULL and the migration is reversible. No data migration required.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_0001"
down_revision: str | None = "20260528_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "complaints",
        sa.Column("submotivo", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "complaints",
        sa.Column("submotivo_2", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "complaints",
        sa.Column("topic", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("complaints", "topic")
    op.drop_column("complaints", "submotivo_2")
    op.drop_column("complaints", "submotivo")
