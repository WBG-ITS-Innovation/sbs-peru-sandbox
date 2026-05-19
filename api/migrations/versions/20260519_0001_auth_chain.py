"""auth chain — institution_certificates, institution_secrets, oauth_clients, institutions.permitted_scopes

Revision ID: 20260519_0001
Revises: 20260518_0001
Create Date: 2026-05-19

Single migration landing the tables needed for the three auth-chain
workstreams of Prompt 7:
- A (mTLS): institution_certificates
- B (HMAC): institution_secrets
- C (OAuth): oauth_clients + institutions.permitted_scopes text[]

The `state` column added to idempotency_records by ADR 0029's
concurrent-POST amendment is **not** in this migration — that lands with
workstream F on Day 2.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260519_0001"
down_revision: str | None = "20260518_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # institutions.permitted_scopes
    op.add_column(
        "institutions",
        sa.Column(
            "permitted_scopes",
            postgresql.ARRAY(sa.String(length=32)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
    )

    # institution_certificates (workstream A — mTLS)
    op.create_table(
        "institution_certificates",
        sa.Column("sha256_thumbprint", sa.String(length=64), primary_key=True),
        sa.Column(
            "institution_id",
            sa.String(length=10),
            sa.ForeignKey("institutions.institution_id"),
            nullable=False,
        ),
        sa.Column("cn", sa.String(length=64), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_institution_certificates_institution_id",
        "institution_certificates",
        ["institution_id"],
    )
    op.create_index(
        "ix_institution_certificates_cn",
        "institution_certificates",
        ["cn"],
    )

    # institution_secrets (workstream B — HMAC)
    op.create_table(
        "institution_secrets",
        sa.Column(
            "institution_id",
            sa.String(length=10),
            sa.ForeignKey("institutions.institution_id"),
            primary_key=True,
        ),
        sa.Column("active_secret", sa.LargeBinary(length=64), nullable=False),
        sa.Column("previous_secret", sa.LargeBinary(length=64), nullable=True),
        sa.Column(
            "previous_secret_retires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "rotated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # oauth_clients (workstream C — OAuth)
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.String(length=64), primary_key=True),
        sa.Column(
            "institution_id",
            sa.String(length=10),
            sa.ForeignKey("institutions.institution_id"),
            nullable=False,
        ),
        sa.Column("client_secret_hash", sa.String(length=256), nullable=False),
        sa.Column(
            "cert_thumbprint_required", sa.String(length=64), nullable=True
        ),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_oauth_clients_institution_id",
        "oauth_clients",
        ["institution_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_oauth_clients_institution_id", table_name="oauth_clients")
    op.drop_table("oauth_clients")
    op.drop_table("institution_secrets")
    op.drop_index(
        "ix_institution_certificates_cn", table_name="institution_certificates"
    )
    op.drop_index(
        "ix_institution_certificates_institution_id",
        table_name="institution_certificates",
    )
    op.drop_table("institution_certificates")
    op.drop_column("institutions", "permitted_scopes")
