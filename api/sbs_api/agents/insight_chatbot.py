"""Insight chatbot agent (P-RESHAPE-7).

Persona-scoped, tool-constrained, provenance-mandatory, on-prem only.

The loop:
1. Build the persona's permitted tool inventory (the LLM never sees a
   tool it cannot use — scope is enforced at the dispatcher, not by
   prompting).
2. Ask the provider for the next turn (tool calls or final text), capped
   at ``MAX_TOOL_CALLS_PER_TURN`` dispatched calls.
3. Dispatch each tool call (re-checking scope + validating params),
   collecting citations.
4. On a final text answer, validate it: an answer that references
   entities (institution codes, pattern types, numbers) must carry at
   least one citation. An uncited entity-referencing answer is a
   validation failure → deterministic template fallback built from the
   tool results.

Cloud is rejected (RuntimeError) — on-prem only in v1.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.agents.insight_chatbot_scope import is_aggregate_only, permitted_tools
from sbs_api.agents.insight_chatbot_tools import (
    ToolResult,
    dispatch_tool,
    tool_inventory,
)
from sbs_api.agents.providers import get_provider
from sbs_api.agents.providers.base import ModelProvider

log = logging.getLogger(__name__)

AGENT_ID = "insight-chatbot"
MODEL_ID_TEMPLATE_FALLBACK = "chatbot-template-fallback-v1"
MAX_TOOL_CALLS_PER_TURN = 5
_ALLOWED_PROVIDERS = {"on_prem", "replay", "mock"}

SYSTEM_PROMPT = (
    "Eres el asistente de análisis de la SBS. Respondes preguntas sobre los "
    "datos usando ÚNICAMENTE las herramientas disponibles; nunca inventes "
    "cifras ni nombres. Cada afirmación con datos debe provenir de una "
    "herramienta. Responde en español (primario) y luego en inglés."
)

# Entities that, if referenced in an answer, require a citation.
_ENTITY_PATTERN = re.compile(
    r"(SBS-\d{3,6}|VOLUME_SPIKE|SUSTAINED_ELEVATION|CROSS_SOURCE_CORRELATION|"
    r"NEW_TOPIC_EMERGENCE|FRAUD_EMERGENCE|\bHIGH\b|\bMEDIUM\b|\d+)"
)
# Phrases that are pure greeting / capability and need no citation.
_NO_CITATION_OK = re.compile(
    r"(qué puedes|que puedes|what can you|hola|hello|capacidad|capabilities|ayuda|help)",
    re.IGNORECASE,
)


@dataclass
class InsightAnswer:
    answer_text_es: str
    answer_text_en: str
    citations: list[dict[str, Any]]
    tool_call_trace: list[dict[str, Any]]
    model_id: str
    model_provider: str
    session_id: str
    message_id: str
    persona: str
    validation: str = "ok"  # ok | template_fallback

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer_text_es": self.answer_text_es,
            "answer_text_en": self.answer_text_en,
            "citations": self.citations,
            "tool_call_trace": self.tool_call_trace,
            "model_id": self.model_id,
            "model_provider": self.model_provider,
            "session_id": self.session_id,
            "message_id": self.message_id,
            "persona": self.persona,
            "validation": self.validation,
        }


def _references_entities(text: str) -> bool:
    return bool(_ENTITY_PATTERN.search(text or ""))


def _needs_citation(text: str) -> bool:
    if not text:
        return False
    if _NO_CITATION_OK.search(text):
        return False
    return _references_entities(text)


def _template_answer(trace: list[ToolResult]) -> tuple[str, str]:
    """Deterministic answer built from tool results — used when the LLM
    answer fails citation validation, or the model returned no usable
    text."""
    if not trace:
        return (
            "No pude obtener datos para responder con evidencia. Reformula la "
            "pregunta indicando institución, categoría o tipo de patrón.",
            "I could not retrieve evidence to answer. Please rephrase with an "
            "institution, category, or pattern type.",
        )
    parts_es = []
    parts_en = []
    for r in trace:
        if r.error:
            parts_es.append(f"[{r.tool}] no disponible: {r.error}")
            parts_en.append(f"[{r.tool}] unavailable: {r.error}")
            continue
        n = len(r.rows)
        parts_es.append(f"[{r.tool}] devolvió {n} resultado(s).")
        parts_en.append(f"[{r.tool}] returned {n} result(s).")
    return (
        "Resumen basado solo en las herramientas consultadas: "
        + " ".join(parts_es),
        "Summary grounded only in the tools queried: " + " ".join(parts_en),
    )


async def answer_message(
    session: AsyncSession,
    *,
    roles: frozenset[str],
    persona: str,
    session_id: str,
    message_id: str,
    user_text: str,
    history: list[dict[str, Any]] | None = None,
    provider: ModelProvider | None = None,
) -> InsightAnswer:
    """Produce one assistant answer for ``user_text`` under ``roles``."""
    provider = provider or get_provider()
    if provider.name not in _ALLOWED_PROVIDERS:
        raise RuntimeError(
            f"Insight chatbot requires an on-prem provider in v1; got "
            f"'{provider.name}'. Cloud is gated."
        )

    permitted = permitted_tools(roles)
    aggregate_only = is_aggregate_only(roles)
    inventory = tool_inventory(permitted)

    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": user_text})

    trace: list[ToolResult] = []
    citations: list[dict[str, Any]] = []
    tool_call_trace: list[dict[str, Any]] = []
    dispatched = 0
    final_text: str | None = None

    # Bounded loop: each provider turn may request tool calls (capped) or
    # return final text.
    for _ in range(MAX_TOOL_CALLS_PER_TURN + 1):
        resp = await provider.complete(
            messages, tools=inventory, temperature=0.0, agent_name=AGENT_ID
        )
        if resp.tool_calls:
            for call in resp.tool_calls:
                if dispatched >= MAX_TOOL_CALLS_PER_TURN:
                    tool_call_trace.append(
                        {"tool": call.name, "skipped": "per_turn_cap_reached"}
                    )
                    continue
                dispatched += 1
                result = await dispatch_tool(
                    session,
                    name=call.name,
                    params=call.arguments or {},
                    permitted=permitted,
                    aggregate_only=aggregate_only,
                )
                trace.append(result)
                tool_call_trace.append(
                    {
                        "tool": result.tool,
                        "parameters": result.parameters,
                        "row_count": len(result.rows),
                        "error": result.error,
                    }
                )
                if not result.error:
                    citations.append(result.citation())
                # Feed the tool result back to the model.
                messages.append(
                    {
                        "role": "tool",
                        "name": result.tool,
                        "content": str(
                            {"rows": result.rows[:10], "error": result.error}
                        ),
                    }
                )
            if dispatched >= MAX_TOOL_CALLS_PER_TURN:
                # Force a final synthesis turn next iteration by not
                # offering tools again is unnecessary; the loop bound
                # handles runaway. Continue to let the model summarise.
                continue
            continue
        final_text = resp.text or ""
        model_id = resp.model_id
        break
    else:
        final_text = None
        model_id = "unknown"

    model_provider = provider.name

    # Citation validation: an entity-referencing answer must cite.
    validation = "ok"
    if final_text is None or (_needs_citation(final_text) and not citations):
        es, en = _template_answer(trace)
        validation = "template_fallback"
        return InsightAnswer(
            answer_text_es=es,
            answer_text_en=en,
            citations=[r.citation() for r in trace if not r.error],
            tool_call_trace=tool_call_trace,
            model_id=MODEL_ID_TEMPLATE_FALLBACK,
            model_provider="template",
            session_id=session_id,
            message_id=message_id,
            persona=persona,
            validation=validation,
        )

    # The model produced a usable, citation-backed (or citation-free
    # greeting) answer. We keep its text as ES and mirror to EN if the
    # provider did not split languages (mock/replay return a single blob).
    return InsightAnswer(
        answer_text_es=final_text,
        answer_text_en=final_text,
        citations=citations,
        tool_call_trace=tool_call_trace,
        model_id=model_id,
        model_provider=model_provider,
        session_id=session_id,
        message_id=message_id,
        persona=persona,
        validation=validation,
    )
