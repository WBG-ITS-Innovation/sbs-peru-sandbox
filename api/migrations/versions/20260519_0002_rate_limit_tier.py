# SPDX-License-Identifier: Apache-2.0
"""rate-limit tier — institutions.tier_classification + rate_limit override

Revision ID: 20260519_0002
Revises: 20260519_0001
Create Date: 2026-05-19

ADR 0033 amendments to the institutions table:
- Add ``tier_classification`` (large|small). Default 'small' so any
  institution that pre-existed without an explicit tier gets the safer
  default.
- Make ``rate_limit_per_minute`` nullable. NULL means "use the tier
  default"; a non-null value overrides the tier.

Existing data is migrated:
- All current rows get ``tier_classification='small'`` from the column
  default.
- The demo rows get explicit settings: BANCO_DEMO_001=large,
  COOPAC_DEMO_002=small (matches the operator seed).
- Existing rate_limit_per_minute values (60 from the Prompt 6 default)
  are NULLed so they pick up tier defaults; the override path is the
  operator's escape hatch, not the steady state.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260519_0002"
down_revision: str | None = "20260519_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "institutions",
        sa.Column(
            "tier_classification",
            sa.String(length=8),
            nullable=False,
            server_default="small",
        ),
    )
    # Allow rate_limit_per_minute to be NULL — null means "use tier default".
    op.alter_column(
        "institutions",
        "rate_limit_per_minute",
        existing_type=sa.Integer(),
        nullable=True,
        existing_server_default="60",
    )
    op.execute(
        """
        UPDATE institutions
        SET rate_limit_per_minute = NULL
        WHERE rate_limit_per_minute = 60
        """
    )
    # Demo data: BANCO=large. COOPAC stays small (column default).
    op.execute(
        """
        UPDATE institutions
        SET tier_classification = 'large'
        WHERE institution_id = 'SBS-001234'
        """
    )


def downgrade() -> None:
    # Restore rate_limit_per_minute=60 where NULL so the NOT NULL re-add
    # does not fail.
    op.execute(
        """
        UPDATE institutions
        SET rate_limit_per_minute = 60
        WHERE rate_limit_per_minute IS NULL
        """
    )
    op.alter_column(
        "institutions",
        "rate_limit_per_minute",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.drop_column("institutions", "tier_classification")
