# SPDX-License-Identifier: Apache-2.0
"""ReplayProvider — load pre-recorded turn sequences from disk.

For the May 27 demo, the cross-source-correlator scaffold agent uses
this provider end-to-end. The real
agents also fall back to it when the runtime is asked for
deterministic behaviour on a known fixture complaint (e.g. the demo
invariant test for BCO-2026-000001).

Fixture layout: ``fixtures/replay/<agent_name>/<complaint_id>.json``.
The file shape is the same as the mock script — a list of turns —
plus an optional ``model_id`` and ``final_output`` override the
runtime stamps onto the agent_run when the script ends.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sbs_api.agents.providers.base import ModelProvider, ModelResponse, ToolCallRequest

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "replay"


class ReplayFixtureMissing(LookupError):
    """No fixture file exists for ``(agent_name, complaint_id)``."""


class ReplayProvider:
    """Reads a replay fixture and emits turns in order."""

    name = "replay"

    def __init__(self, fixture_root: Path | None = None):
        self._root = fixture_root or FIXTURE_ROOT
        self._cursors: dict[tuple[str, str], int] = {}
        self._cache: dict[tuple[str, str], dict[str, Any]] = {}

    def _load(self, agent_name: str, complaint_id: str) -> dict[str, Any]:
        key = (agent_name, complaint_id)
        if key in self._cache:
            return self._cache[key]
        path = self._root / agent_name / f"{complaint_id}.json"
        if not path.exists():
            # Generic default fixture lets the runtime exercise an agent
            # without a complaint-specific recording.
            default = self._root / agent_name / "_default.json"
            if not default.exists():
                raise ReplayFixtureMissing(
                    f"No replay fixture for agent={agent_name!r} "
                    f"complaint={complaint_id!r}"
                )
            path = default
        data = json.loads(path.read_text(encoding="utf-8"))
        self._cache[key] = data
        return data

    def fixture(self, agent_name: str, complaint_id: str) -> dict[str, Any]:
        """Public read-only accessor used by tests and agent shells."""
        return self._load(agent_name, complaint_id)

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
        if not agent_name or not complaint_id:
            raise ValueError(
                "ReplayProvider requires both agent_name and complaint_id"
            )

        data = self._load(agent_name, complaint_id)
        script = data.get("turns") or []
        key = (agent_name, complaint_id)
        idx = self._cursors.get(key, 0)
        turn = script[idx] if idx < len(script) else {"text": ""}
        self._cursors[key] = idx + 1

        model_id = data.get("model_id", "replay-1")

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
                model_id=model_id,
                finish_reason="tool_calls",
            )

        return ModelResponse(
            served_by=self.name,
            text=turn.get("text", ""),
            model_id=model_id,
            finish_reason="stop",
        )

    def reset(self) -> None:
        self._cursors.clear()
