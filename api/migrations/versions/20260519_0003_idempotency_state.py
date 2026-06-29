# SPDX-License-Identifier: Apache-2.0
"""idempotency state — placeholder-INSERT pattern for concurrent POSTs

Revision ID: 20260519_0003
Revises: 20260519_0002
Create Date: 2026-05-19

ADR 0029 amendment (concurrent-POST policy): the
``idempotency_records`` row gains a ``state`` column. The handler now
INSERTs a placeholder row with ``state='processing'`` and the unique
constraint ``(institution_id, idempotency_key)``, proceeds with the
business logic, and UPDATEs the row to ``state='complete'`` with the
response payload. A second, concurrent request whose INSERT loses the
unique-constraint race reads the existing row and either returns the
cached response (state='complete') or waits 50ms × 3 retries for the
first request to complete; if not complete within 150ms, returns 409
``IDEMPOTENCY_KEY_IN_FLIGHT`` with ``Retry-After: 1``.

Existing rows default to ``state='complete'`` so the migration is
backwards-compatible: rows written by the Prompt 6 implementation are
treated as already-complete cached responses.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260519_0003"
down_revision: str | None = "20260519_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "idempotency_records",
        sa.Column(
            "state",
            sa.String(length=16),
            nullable=False,
            server_default="complete",
        ),
    )
    op.create_index(
        "ix_idem_state", "idempotency_records", ["state"]
    )


def downgrade() -> None:
    op.drop_index("ix_idem_state", table_name="idempotency_records")
    op.drop_column("idempotency_records", "state")
