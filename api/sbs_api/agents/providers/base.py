# SPDX-License-Identifier: Apache-2.0
"""Model-provider protocol.

The agent runtime depends only on this protocol — never on a concrete
provider. Concrete providers (on-prem vLLM, Azure OpenAI cloud, replay
fixtures, test-only mock) implement ``complete()`` and are selected by
env var.

A provider that cannot serve a request raises
:class:`ProviderUnavailableError`. No provider substitutes canned output
for a real completion.

A ``ModelResponse`` is intentionally shaped like a typical chat
completion: either ``text`` (final answer) or ``tool_calls`` (next
hop). ``finish_reason`` is one of ``stop`` | ``tool_calls`` |
``length`` | ``error``. ``usage`` is best-effort; replay/mock report
zeros.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class ProviderUnavailableError(RuntimeError):
    """The configured provider cannot serve the request.

    Raised instead of silently degrading to canned output. Before this
    existed, :class:`~sbs_api.agents.providers.on_prem.OnPremProvider`
    answered from :class:`~sbs_api.agents.providers.mock.MockProvider`
    whenever the vLLM endpoint was unset or unreachable, so an
    unconfigured host produced agent_runs indistinguishable — from the
    caller's side — from real inference. A supervisory tool must fail
    loudly rather than fabricate an analysis, so the fallback is gone
    and this is what a missing backend looks like now.

    Carries the provider name and a human-readable reason; the boot
    healthcheck turns it into an operator-facing message. Never carries
    a credential.
    """

    def __init__(self, provider: str, reason: str) -> None:
        self.provider = provider
        self.reason = reason
        super().__init__(f"provider {provider!r} unavailable: {reason}")


@dataclass(frozen=True)
class ToolCallRequest:
    """A tool the model wants the runtime to execute next."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class ModelResponse:
    text: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model_id: str = "unknown"
    latency_ms: int = 0
    finish_reason: str = "stop"
    # Name of the provider that ACTUALLY produced this response, so
    # "which model answered?" is answerable from the database alone.
    # Every provider stamps it; ``replay`` stamping it is what lets a
    # reader tell a replayed fixture from live inference. Persisted to
    # agent_runs.model_provider.
    served_by: str | None = None


@runtime_checkable
class ModelProvider(Protocol):
    """The single point of contact between agents and any LLM-shaped backend.

    Implementations must be safe to share across requests (the factory
    caches one instance per process).
    """

    name: str

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
        """Produce the next assistant turn.

        ``messages`` is the OpenAI-style array (system, user,
        assistant, tool) the runtime has accumulated so far.
        ``tools`` is the JSON-Schema declarations of tools the agent
        is allowed to call. The provider returns either a final
        ``text`` answer or one or more ``tool_calls``.
        """
        ...
