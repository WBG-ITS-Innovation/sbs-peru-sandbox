"""Widen complaints.submotivo_2 for clustered descriptive phrases.

Revision ID: 20260529_0002
Revises: 20260529_0001
Create Date: 2026-05-29

submotivo_2 now carries full descriptive sentences (~8–15 words — the kind a
clustering model surfaces), which exceed the original 64-char limit. Widen to
255. submotivo and topic stay short single labels and are unchanged.

Downgrade narrows back to 64; it will error if any value longer than 64 chars
remains, so clear oversized submotivo_2 values before downgrading.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_0002"
down_revision: str | None = "20260529_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "complaints",
        "submotivo_2",
        existing_type=sa.String(length=64),
        type_=sa.String(length=255),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "complaints",
        "submotivo_2",
        existing_type=sa.String(length=255),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
