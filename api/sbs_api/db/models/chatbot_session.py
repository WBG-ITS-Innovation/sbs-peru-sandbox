"""Chatbot session + message ORM models (P-RESHAPE-7).

The insight chatbot is the supervisors' daily-use surface. Sessions and
messages are persisted for audit: every assistant answer carries the
tool-call trace + citations that produced it, so any answer can be
reconstructed. User-message ``content`` is stored ALREADY anonymized
(the existing redaction engine runs at ingestion, before storage and
before the LLM sees it).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base

CHATBOT_MESSAGE_ROLES = ("user", "assistant", "tool")


class ChatbotSession(Base):
    __tablename__ = "chatbot_sessions"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    persona: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    __table_args__ = (
        Index("ix_chatbot_sessions_user_activity", "user_id", "last_activity_at"),
    )


class ChatbotMessage(Base):
    __tablename__ = "chatbot_messages"

    message_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chatbot_sessions.session_id"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # User-message content is stored ALREADY anonymized.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    citations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    model_provider: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('user','assistant','tool')",
            name="ck_chatbot_messages_role",
        ),
        Index("ix_chatbot_messages_session", "session_id", "created_at"),
    )
