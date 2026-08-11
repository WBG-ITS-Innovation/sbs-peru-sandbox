# SPDX-License-Identifier: Apache-2.0
"""MockProvider — deterministic stub for tests and CI.

Returns canned tool-call sequences keyed by ``agent_name`` so the
runtime can be exercised end-to-end without any real model. Tests
that need a specific tool sequence inject their own
``script`` via :func:`MockProvider.with_script`.

**Script cursors are keyed by ``(agent_name, complaint_id)``**, the same
way :class:`~sbs_api.agents.providers.replay.ReplayProvider` keys its
own. Every complaint therefore replays its agent's script from the top,
however many complaints the process has already served.

This used to be keyed by ``agent_name`` alone. ``get_provider()`` caches
one instance per process, and the only ``reset()`` call sites are guarded
by ``isinstance(provider, ReplayProvider)``, so a MockProvider cursor
advanced monotonically for the life of the process and ran off the end of
its script after the first complaint. Past the end ``complete()`` returns
``{"text": ""}`` — no tool calls — so the first complaint a process saw
got a real agent run and every complaint after it got a hollow one:
``tool_calls=[]``, ``other @ 0.55``, ``route_to=info-only``, and no
investigation/synthesis/correlator stage at all. That is the default
posture on any host without a vLLM, because ``on_prem`` falls back here.
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
    "cross-source-correlator": [
        {
            "tool_calls": [
                {"name": "compute_anomaly_score", "arguments": {}},
                {"name": "search_similar_complaints", "arguments": {}},
            ]
        },
        {"text": "correlator-complete"},
    ],
}


class MockProvider:
    """Deterministic, scriptable provider for tests and CI."""

    name = "mock"

    # Sentinel key segment for callers that pass no complaint_id. Such
    # calls share one cursor, which is the old behaviour and is what a
    # complaint-less unit test wants.
    _NO_COMPLAINT = "-"

    def __init__(self, scripts: dict[str, list[dict[str, Any]]] | None = None):
        self._scripts = scripts or DEFAULT_SCRIPTS
        self._cursors: dict[tuple[str, str], int] = {}

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
        # Per (agent, complaint) cursor — see the module docstring for why
        # a per-agent cursor silently hollowed out every complaint after
        # the first one a process served.
        key = (agent, complaint_id or self._NO_COMPLAINT)
        idx = self._cursors.get(key, 0)
        turn = script[idx] if idx < len(script) else {"text": ""}
        self._cursors[key] = idx + 1

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
                served_by=self.name,
                text=None,
                tool_calls=calls,
                model_id="mock-1",
                finish_reason="tool_calls",
            )

        return ModelResponse(
            served_by=self.name,
            text=turn.get("text", ""),
            model_id="mock-1",
            finish_reason="stop",
        )

    @classmethod
    def with_script(
        cls, scripts: dict[str, list[dict[str, Any]]]
    ) -> "MockProvider":
        return cls(scripts=scripts)
