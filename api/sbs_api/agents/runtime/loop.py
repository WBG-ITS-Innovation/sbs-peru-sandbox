# SPDX-License-Identifier: Apache-2.0
"""Tool-calling loop.

Pure orchestration: the loop alternates between provider.complete()
and tool executions until the provider returns a final text response
or ``max_iterations`` is hit. Every tool call is captured as a
:class:`ToolCallRecord` and the assembled trace becomes the
``tool_calls`` JSONB column on the agent_run row.

The loop intentionally does NOT write to ``agent_runs`` — that is
the agent's responsibility, because the agent owns the
``final_output`` shape.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sbs_api.agents.providers.base import ModelProvider, ModelResponse
from sbs_api.agents.tools.base import (
    ToolCallRecord,
    ToolContext,
    execute_tool,
    tools_for,
)

log = logging.getLogger(__name__)

# OpenTelemetry is wired into the FastAPI app via ADR 0028. Importing it
# at module scope so the agent runtime emits spans from its first commit
# (Principle 3). The ``no-op`` tracer is used when OTel isn't installed.
try:
    from opentelemetry import trace as _otel_trace

    _tracer = _otel_trace.get_tracer("sbs_api.agents.runtime")
except Exception:  # noqa: BLE001
    _tracer = None  # type: ignore[assignment]

MAX_ITERATIONS_DEFAULT = 5


@dataclass
class LoopResult:
    text: str | None
    tool_call_records: list[ToolCallRecord] = field(default_factory=list)
    iterations: int = 0
    finish_reason: str = "stop"
    model_id: str = "unknown"
    # Provider that actually served the last completion — "mock" when
    # OnPremProvider fell back, not the configured "on_prem". Written to
    # agent_runs.model_provider by the agents.
    served_by: str | None = None


@dataclass
class LoopConfig:
    agent_name: str
    agent_version: str
    system_prompt: str
    allowed_tools: list[str]
    complaint_id: str
    max_iterations: int = MAX_ITERATIONS_DEFAULT
    temperature: float = 0.0
    on_iteration: Callable[[int, ModelResponse], None] | None = None


async def run_loop(
    provider: ModelProvider,
    ctx: ToolContext,
    config: LoopConfig,
    *,
    user_prompt: str | None = None,
) -> LoopResult:
    tools_schema = [t.to_openai_schema() for t in tools_for(config.allowed_tools)]

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": config.system_prompt}
    ]
    messages.append(
        {
            "role": "user",
            "content": user_prompt
            or f"Analiza el reclamo {config.complaint_id} usando los tools disponibles.",
        }
    )

    tool_call_records: list[ToolCallRecord] = []
    final_text: str | None = None
    finish_reason = "stop"
    model_id = "unknown"
    served_by: str | None = None

    for iteration in range(1, config.max_iterations + 1):
        span_cm = (
            _tracer.start_as_current_span(
                "agent.iteration",
                attributes={
                    "agent.name": config.agent_name,
                    "agent.version": config.agent_version,
                    "agent.complaint_id": config.complaint_id,
                    "agent.iteration": iteration,
                },
            )
            if _tracer is not None
            else _NullContext()
        )
        with span_cm:
            response = await provider.complete(
                messages,
                tools=tools_schema,
                temperature=config.temperature,
                agent_name=config.agent_name,
                complaint_id=config.complaint_id,
            )
            model_id = response.model_id
            served_by = response.served_by or served_by
            finish_reason = response.finish_reason
            log.info(
                "agent_iteration",
                extra={
                    "agent_name": config.agent_name,
                    "agent_version": config.agent_version,
                    "complaint_id": config.complaint_id,
                    "iteration": iteration,
                    "finish_reason": finish_reason,
                    "model_id": model_id,
                    "tool_call_count": len(response.tool_calls),
                },
            )
            if config.on_iteration is not None:
                try:
                    config.on_iteration(iteration, response)
                except Exception:  # noqa: BLE001
                    log.exception("on_iteration hook raised; continuing")

        if not response.tool_calls:
            final_text = response.text
            break

        assistant_message: dict[str, Any] = {"role": "assistant"}
        if response.text:
            assistant_message["content"] = response.text
        assistant_message["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    # Preserve the arguments the model emitted so multi-turn
                    # context survives. OpenAI's tool-call shape requires a
                    # JSON-stringified arguments field — empty objects are
                    # serialised as ``"{}"``, not the literal Python dict.
                    "arguments": json.dumps(tc.arguments or {}, default=str),
                },
            }
            for tc in response.tool_calls
        ]
        messages.append(assistant_message)

        # Run requested tools in parallel; preserve call order in trace.
        async def _run(name: str, args: dict[str, Any]) -> ToolCallRecord:
            if name not in config.allowed_tools:
                return ToolCallRecord(
                    tool_name=name,
                    tool_version="0.0.0",
                    started_at=datetime.now(tz=timezone.utc),
                    ended_at=datetime.now(tz=timezone.utc),
                    input=args,
                    output=None,
                    status="failed",
                    error={
                        "code": "TOOL_NOT_ALLOWED",
                        "message": f"agent {config.agent_name!r} cannot call {name!r}",
                    },
                )
            return await execute_tool(name, ctx, args)

        results = await asyncio.gather(
            *(_run(tc.name, tc.arguments) for tc in response.tool_calls)
        )
        for tc, record in zip(response.tool_calls, results):
            tool_call_records.append(record)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": _serialise_tool_output(record),
                }
            )

    return LoopResult(
        text=final_text,
        tool_call_records=tool_call_records,
        iterations=iteration,
        finish_reason=finish_reason,
        model_id=model_id,
        served_by=served_by,
    )


def _serialise_tool_output(record: ToolCallRecord) -> str:
    if record.status != "success":
        return json.dumps(
            {"status": record.status, "error": record.error},
            default=str,
        )
    return json.dumps(record.output or {}, default=str)


class _NullContext:
    """No-op context manager used when OpenTelemetry isn't installed."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False
