# SPDX-License-Identifier: Apache-2.0
"""Tool registry and the ``Tool`` base class.

Every agent tool subclasses :class:`Tool`, declares a JSON Schema
for its parameters, and implements :meth:`run`. Tools register
themselves via the :func:`register_tool` decorator and the runtime
discovers them by name. The names listed here also appear in
``docs/schemas/agent_run.schema.json`` (tool_name enum) — adding a
new tool requires extending that enum.

Tools deliberately do not write to ``agent_runs`` themselves; the
runtime captures the call and produces the tool_call record. Tools
may write to ``audit_events`` when they take a side-effectful step
(``log_taxonomy_unknown`` is the only such tool today).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ToolContext:
    """Per-call execution context handed to every tool.

    Tools that need the DB read from ``session``. Tools that need
    deterministic-fixture behaviour for the demo path inspect
    ``replay_complaint_id`` and short-circuit accordingly.
    """

    session: AsyncSession | None = None
    complaint_id: str | None = None
    agent_name: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallRecord:
    """The runtime's view of a single tool invocation.

    Serialised into the ``agent_runs.tool_calls`` JSONB column and
    constrained by ``docs/schemas/agent_run.schema.json``.
    """

    tool_name: str
    tool_version: str
    started_at: datetime
    ended_at: datetime
    input: dict[str, Any]
    output: dict[str, Any] | None
    status: str = "success"  # "success" | "failed" | "timeout"
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "started_at": self.started_at.isoformat(timespec="microseconds"),
            "ended_at": self.ended_at.isoformat(timespec="microseconds"),
            "input": self.input,
            "output": self.output,
            "status": self.status,
            "error": self.error,
        }


class Tool:
    """Base class for every agent tool.

    Subclasses set ``name``, ``description``, ``version``, and
    ``parameters`` (JSON Schema for the tool arguments), and
    implement :meth:`run`. The registry maps ``name`` → class.
    """

    name: str = ""
    description: str = ""
    version: str = "0.1.0"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    async def run(self, ctx: ToolContext, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


_REGISTRY: dict[str, Tool] = {}


def register_tool(cls: type[Tool]) -> type[Tool]:
    """Class decorator that registers a tool by its declared name."""
    if not cls.name:
        raise ValueError(f"{cls.__name__} must declare a non-empty name")
    if cls.name in _REGISTRY:
        # Re-registration is benign in test reloads; keep last writer.
        pass
    _REGISTRY[cls.name] = cls()
    return cls


def get_tool(name: str) -> Tool:
    if name not in _REGISTRY:
        raise KeyError(f"No tool registered for name={name!r}")
    return _REGISTRY[name]


def list_tools() -> list[str]:
    return sorted(_REGISTRY.keys())


def tools_for(names: list[str]) -> list[Tool]:
    return [get_tool(n) for n in names]


async def execute_tool(
    name: str,
    ctx: ToolContext,
    arguments: dict[str, Any] | None = None,
) -> ToolCallRecord:
    """Invoke a tool by name and return a structured call record.

    The runtime calls this — tools never call each other directly so
    every invocation is captured for the agent_run trace.
    """
    args = dict(arguments or {})
    tool = get_tool(name)
    started = datetime.now(tz=timezone.utc)
    t0 = time.monotonic()
    try:
        output = await tool.run(ctx, **args)
        ended = datetime.now(tz=timezone.utc)
        return ToolCallRecord(
            tool_name=tool.name,
            tool_version=tool.version,
            started_at=started,
            ended_at=ended,
            input=args,
            output=output,
            status="success",
            error=None,
        )
    except TimeoutError as exc:
        ended = datetime.now(tz=timezone.utc)
        return ToolCallRecord(
            tool_name=tool.name,
            tool_version=tool.version,
            started_at=started,
            ended_at=ended,
            input=args,
            output=None,
            status="timeout",
            error={"code": "TOOL_TIMEOUT", "message": str(exc) or "tool timed out"},
        )
    except Exception as exc:  # noqa: BLE001
        ended = datetime.now(tz=timezone.utc)
        return ToolCallRecord(
            tool_name=tool.name,
            tool_version=tool.version,
            started_at=started,
            ended_at=ended,
            input=args,
            output=None,
            status="failed",
            error={
                "code": "TOOL_ERROR",
                "message": f"{type(exc).__name__}: {exc}"[:300],
            },
        )
