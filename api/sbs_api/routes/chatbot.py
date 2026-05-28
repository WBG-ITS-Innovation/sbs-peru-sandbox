"""Insight-chatbot endpoints (P-RESHAPE-7).

* POST   /v1/chatbot/sessions                       — open a session
* POST   /v1/chatbot/sessions/{id}/messages         — ask a question
* GET    /v1/chatbot/sessions/{id}                  — session history
* DELETE /v1/chatbot/sessions/{id}                  — end (audit-retained)

All routes require the ``chatbot:use`` scope (every internal persona has
it; FI users do not exist). The acting user id arrives on the
``X-SBS-User`` header the BFF forwards; ``session.user_id == caller``
is a hard server check on the message + history + delete routes.

User-message text is anonymized with the existing redaction engine
BEFORE it is stored AND before the LLM sees it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.agents.insight_chatbot import answer_message
from sbs_api.agents.insight_chatbot_limits import check_message_allowed
from sbs_api.auth.persona_scopes import CHATBOT_USE, primary_persona
from sbs_api.db.models.chatbot_session import ChatbotMessage, ChatbotSession
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.persona import parse_roles_header, requires_scope
from sbs_api.redaction.engine import redact
from sbs_api.routes._internal_auth import verify_internal_secret

router = APIRouter(prefix="/chatbot", tags=["Chatbot"])

_CHATBOT = requires_scope(CHATBOT_USE)


def _caller(x_sbs_user: str | None) -> str:
    if not x_sbs_user:
        raise HTTPException(status_code=401, detail="X-SBS-User required")
    return x_sbs_user


async def _load_session(session: AsyncSession, session_id: str) -> ChatbotSession:
    row = (
        await session.execute(
            select(ChatbotSession).where(ChatbotSession.session_id == session_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return row


def _assert_owner(chat: ChatbotSession, caller: str) -> None:
    if chat.user_id != caller:
        # 404 (not 403) so a caller cannot probe another user's session ids.
        raise HTTPException(status_code=404, detail="Session not found")


# --- create session -------------------------------------------------------


@router.post(
    "/sessions",
    status_code=201,
    dependencies=[Depends(verify_internal_secret), Depends(_CHATBOT)],
)
async def create_session(
    session: AsyncSession = Depends(get_session),
    x_sbs_user: str | None = Header(default=None, alias="X-SBS-User"),
    x_sbs_role: str | None = Header(default=None, alias="X-SBS-Role"),
) -> dict[str, Any]:
    caller = _caller(x_sbs_user)
    roles = parse_roles_header(x_sbs_role)
    persona = primary_persona(roles) or "unknown"
    session_id = str(uuid.uuid4())
    session.add(
        ChatbotSession(
            session_id=session_id,
            user_id=caller,
            persona=persona,
            message_count=0,
        )
    )
    await session.flush()
    await session.commit()
    return {"session_id": session_id, "persona": persona}


# --- persona-suggested questions (P-RESHAPE-9) ----------------------------


@router.get(
    "/suggested_questions",
    dependencies=[Depends(verify_internal_secret)],
)
async def suggested_questions(
    roles: frozenset[str] = Depends(_CHATBOT),
) -> dict[str, Any]:
    """Workflow-tuned starter questions for the caller's home persona."""
    from sbs_api.agents.insight_chatbot_suggestions import suggestions_for_roles

    persona = primary_persona(roles) or "unknown"
    questions = suggestions_for_roles(roles)
    return {"persona": persona, "questions": questions}


# --- post message ---------------------------------------------------------


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4_000)


@router.post(
    "/sessions/{session_id}/messages",
    dependencies=[Depends(verify_internal_secret), Depends(_CHATBOT)],
)
async def post_message(
    session_id: str,
    body: MessageRequest,
    session: AsyncSession = Depends(get_session),
    x_sbs_user: str | None = Header(default=None, alias="X-SBS-User"),
    x_sbs_role: str | None = Header(default=None, alias="X-SBS-Role"),
) -> dict[str, Any]:
    caller = _caller(x_sbs_user)
    roles = parse_roles_header(x_sbs_role)
    chat = await _load_session(session, session_id)
    _assert_owner(chat, caller)

    # Rate-limit + abuse guards (structured 429, never silent).
    decision = await check_message_allowed(
        session, user_id=caller, chat_session=chat
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=429,
            detail={"error": "rate_limited", "reason": decision.reason},
        )

    now = datetime.now(tz=timezone.utc)
    # Anonymize the user message BEFORE storage + before the LLM sees it.
    redacted_text = redact(body.content).redacted_text

    user_msg_id = str(uuid.uuid4())
    session.add(
        ChatbotMessage(
            message_id=user_msg_id,
            session_id=session_id,
            role="user",
            content=redacted_text,
        )
    )
    chat.message_count += 1
    chat.last_activity_at = now
    await session.flush()

    # Build short history (prior turns) for context.
    prior = (
        await session.execute(
            select(ChatbotMessage)
            .where(ChatbotMessage.session_id == session_id)
            .where(ChatbotMessage.role.in_(["user", "assistant"]))
            .order_by(ChatbotMessage.created_at.desc())
            .limit(10)
        )
    ).scalars().all()
    history = [
        {"role": m.role, "content": m.content}
        for m in reversed(prior)
        if m.message_id != user_msg_id
    ]

    assistant_msg_id = str(uuid.uuid4())
    answer = await answer_message(
        session,
        roles=roles,
        persona=chat.persona,
        session_id=session_id,
        message_id=assistant_msg_id,
        user_text=redacted_text,
        history=history,
    )

    session.add(
        ChatbotMessage(
            message_id=assistant_msg_id,
            session_id=session_id,
            role="assistant",
            content=answer.answer_text_es,
            tool_calls={"trace": answer.tool_call_trace},
            citations={"items": answer.citations},
            model_id=answer.model_id,
            model_provider=answer.model_provider,
        )
    )
    chat.message_count += 1
    chat.last_activity_at = datetime.now(tz=timezone.utc)
    await session.flush()
    await session.commit()

    return answer.to_dict()


# --- session history ------------------------------------------------------


@router.get(
    "/sessions/{session_id}",
    dependencies=[Depends(verify_internal_secret), Depends(_CHATBOT)],
)
async def get_session_history(
    session_id: str,
    session: AsyncSession = Depends(get_session),
    x_sbs_user: str | None = Header(default=None, alias="X-SBS-User"),
) -> dict[str, Any]:
    caller = _caller(x_sbs_user)
    chat = await _load_session(session, session_id)
    _assert_owner(chat, caller)
    msgs = (
        await session.execute(
            select(ChatbotMessage)
            .where(ChatbotMessage.session_id == session_id)
            .order_by(ChatbotMessage.created_at.asc())
        )
    ).scalars().all()
    return {
        "session_id": session_id,
        "persona": chat.persona,
        "ended_at": chat.ended_at.isoformat() if chat.ended_at else None,
        "messages": [
            {
                "message_id": m.message_id,
                "role": m.role,
                "content": m.content,
                "citations": m.citations,
                "model_id": m.model_id,
                "created_at": m.created_at.isoformat(timespec="seconds"),
            }
            for m in msgs
        ],
    }


# --- end session ----------------------------------------------------------


@router.delete(
    "/sessions/{session_id}",
    dependencies=[Depends(verify_internal_secret), Depends(_CHATBOT)],
)
async def end_session(
    session_id: str,
    session: AsyncSession = Depends(get_session),
    x_sbs_user: str | None = Header(default=None, alias="X-SBS-User"),
) -> dict[str, Any]:
    caller = _caller(x_sbs_user)
    chat = await _load_session(session, session_id)
    _assert_owner(chat, caller)
    if chat.ended_at is None:
        chat.ended_at = datetime.now(tz=timezone.utc)
        await session.flush()
        await session.commit()
    # Messages are audit-retained — not deleted.
    return {"session_id": session_id, "status": "ended"}
