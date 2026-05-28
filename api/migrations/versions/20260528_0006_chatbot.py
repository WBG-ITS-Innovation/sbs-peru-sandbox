"""P-RESHAPE-7 — chatbot_sessions + chatbot_messages.

Revision ID: 20260528_0006
Revises: 20260528_0005
Create Date: 2026-05-28

Storage for the insight chatbot. Sessions + audit-retained messages;
assistant messages carry the tool-call trace + citations that produced
the answer. Additive.
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260528_0006"
down_revision: str | None = "20260528_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chatbot_sessions",
        sa.Column("session_id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("persona", sa.String(length=32), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "message_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index(
        "ix_chatbot_sessions_user_activity",
        "chatbot_sessions",
        ["user_id", "last_activity_at"],
    )

    op.create_table(
        "chatbot_messages",
        sa.Column("message_id", sa.String(length=36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("chatbot_sessions.session_id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "tool_calls",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("model_id", sa.String(length=96), nullable=True),
        sa.Column("model_provider", sa.String(length=16), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "role IN ('user','assistant','tool')",
            name="ck_chatbot_messages_role",
        ),
    )
    op.create_index(
        "ix_chatbot_messages_session",
        "chatbot_messages",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chatbot_messages_session", table_name="chatbot_messages")
    op.drop_table("chatbot_messages")
    op.drop_index(
        "ix_chatbot_sessions_user_activity", table_name="chatbot_sessions"
    )
    op.drop_table("chatbot_sessions")
