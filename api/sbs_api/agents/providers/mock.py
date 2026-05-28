"""MockProvider — deterministic stub for tests and CI.

Returns canned tool-call sequences keyed by ``agent_name`` so the
runtime can be exercised end-to-end without any real model. Tests
that need a specific tool sequence inject their own
``script`` via :func:`MockProvider.with_script`.
"""

from __future__ import annotations

import uuid
from typing import Any

from sbs_api.agents.providers.base import ModelProvider, ModelResponse, ToolCallRequest

# Per-agent default scripts. Each script is a list of "turns". Each
# turn is either ``{"tool_calls": [{"name": ..., "arguments": {...}}, ...]}``
# or ``{"text": "..."}``. The mock returns turns in order and emits a
# final empty-text response if the script runs out.
DEFAULT_SCRIPTS: dict[str, list[dict[str, Any]]] = {
    "triage": [
        {
            "tool_calls": [
                {"name": "query_dq_results", "arguments": {}},
                {"name": "query_taxonomy_normalizations", "arguments": {}},
                {"name": "classify_complaint", "arguments": {}},
            ]
        },
        {"text": "triage-complete"},
    ],
    "investigation": [
        {
            "tool_calls": [
                {"name": "rank_features", "arguments": {}},
                {"name": "compute_anomaly_score", "arguments": {}},
                {"name": "search_similar_complaints", "arguments": {}},
            ]
        },
        {"tool_calls": [{"name": "draft_narrative", "arguments": {}}]},
        {"text": "investigation-complete"},
    ],
    "synthesis": [
        {
            "tool_calls": [
                {"name": "query_audit_chain", "arguments": {}},
                {"name": "summarize_for_executive", "arguments": {}},
            ]
        },
        {"text": "synthesis-complete"},
    ],
}


class MockProvider:
    """Deterministic, scriptable provider for tests and CI."""

    name = "mock"

    def __init__(self, scripts: dict[str, list[dict[str, Any]]] | None = None):
        self._scripts = scripts or DEFAULT_SCRIPTS
        self._cursors: dict[str, int] = {}

    def reset(self) -> None:
        self._cursors.clear()

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        agent_name: str | None = None,
        complaint_id: str | None = None,
    ) -> ModelResponse:
        agent = agent_name or "default"
        script = self._scripts.get(agent, [{"text": "ok"}])
        idx = self._cursors.get(agent, 0)
        turn = script[idx] if idx < len(script) else {"text": ""}
        self._cursors[agent] = idx + 1

        if "tool_calls" in turn:
            calls = [
                ToolCallRequest(
                    id=f"call-{uuid.uuid4().hex[:8]}",
                    name=tc["name"],
                    arguments=tc.get("arguments", {}),
                )
                for tc in turn["tool_calls"]
            ]
            return ModelResponse(
                text=None,
                tool_calls=calls,
                model_id="mock-1",
                finish_reason="tool_calls",
            )

        return ModelResponse(
            text=turn.get("text", ""),
            model_id="mock-1",
            finish_reason="stop",
        )

    @classmethod
    def with_script(
        cls, scripts: dict[str, list[dict[str, Any]]]
    ) -> "MockProvider":
        return cls(scripts=scripts)
