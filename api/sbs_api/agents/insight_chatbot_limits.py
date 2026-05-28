"""Insight-chatbot rate limits + abuse guards (P-RESHAPE-7).

DB-backed counters (no Redis dependency on the chat path): per-user
hourly + daily message caps, per-session message cap + idle timeout, and
the per-turn tool-call cap. Every rejection is a structured result the
caller turns into a 429 with a reason — never a silent drop.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.chatbot_session import ChatbotMessage, ChatbotSession

# Locked limits.
PER_USER_HOURLY = 60
PER_USER_DAILY = 200
PER_SESSION_MESSAGES = 50
SESSION_IDLE_TIMEOUT = timedelta(hours=1)
TOOL_CALLS_PER_TURN = 5


@dataclass(frozen=True)
class LimitDecision:
    allowed: bool
    reason: str | None = None


async def check_message_allowed(
    session: AsyncSession,
    *,
    user_id: str,
    chat_session: ChatbotSession,
    now: datetime | None = None,
) -> LimitDecision:
    """Evaluate every per-user + per-session guard before accepting a
    user message. Returns the first failing reason, or allowed=True."""
    now = now or datetime.now(tz=timezone.utc)

    if chat_session.ended_at is not None:
        return LimitDecision(False, "session_ended")

    # Idle timeout.
    if chat_session.last_activity_at is not None:
        idle = now - chat_session.last_activity_at
        if idle > SESSION_IDLE_TIMEOUT:
            return LimitDecision(False, "session_idle_timeout")

    # Per-session message cap.
    if chat_session.message_count >= PER_SESSION_MESSAGES:
        return LimitDecision(False, "session_message_cap")

    # Per-user hourly cap (user-role messages across the user's sessions).
    hour_ago = now - timedelta(hours=1)
    hourly = (
        await session.execute(
            select(func.count())
            .select_from(ChatbotMessage)
            .join(
                ChatbotSession,
                ChatbotSession.session_id == ChatbotMessage.session_id,
            )
            .where(ChatbotSession.user_id == user_id)
            .where(ChatbotMessage.role == "user")
            .where(ChatbotMessage.created_at >= hour_ago)
        )
    ).scalar_one()
    if hourly >= PER_USER_HOURLY:
        return LimitDecision(False, "user_hourly_cap")

    # Per-user daily cap.
    day_ago = now - timedelta(days=1)
    daily = (
        await session.execute(
            select(func.count())
            .select_from(ChatbotMessage)
            .join(
                ChatbotSession,
                ChatbotSession.session_id == ChatbotMessage.session_id,
            )
            .where(ChatbotSession.user_id == user_id)
            .where(ChatbotMessage.role == "user")
            .where(ChatbotMessage.created_at >= day_ago)
        )
    ).scalar_one()
    if daily >= PER_USER_DAILY:
        return LimitDecision(False, "user_daily_cap")

    return LimitDecision(True)
