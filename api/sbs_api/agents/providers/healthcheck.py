# SPDX-License-Identifier: Apache-2.0
"""Boot healthcheck — one canary tool-call against the configured provider.

Answers the question the old silent fallback made unanswerable at boot:
*will this process actually get live tool-calling inference, or not?* It
sends a single request carrying one trivial tool declaration and asserts
the provider comes back with a non-empty ``tool_calls`` list. A provider
that answers with prose instead of a tool call cannot drive the agent
runtime — every agent in this codebase is tool-calling only — so an empty
``tool_calls`` is a failure, not a warning.

Two ways in:

* ``await check_provider()`` — used by the FastAPI lifespan when
  ``SBS_API_AGENTS_PIPELINE_ENABLED`` is on, and by the CLI below.
* ``python scripts/provider_healthcheck.py`` — the operator-facing form,
  exits 0 or 1 with a readable message.

The canary costs one completion. It is skipped for ``replay`` and
``mock``, which read from disk and would only ever prove the disk works.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sbs_api.agents.providers import get_provider
from sbs_api.agents.providers.base import ModelProvider, ProviderUnavailableError

log = logging.getLogger(__name__)

CANARY_AGENT_NAME = "provider-healthcheck"
CANARY_COMPLAINT_ID = "HEALTHCHECK-0000"

# One tool, one required string argument. Deliberately trivial: the point
# is to prove the round trip and the tool-calling surface, not to test the
# model's judgement.
CANARY_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "provider_canary",
            "description": (
                "Health probe. Call this tool with value='ok' and nothing "
                "else."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "string",
                        "description": "Always the literal string 'ok'.",
                    }
                },
                "required": ["value"],
            },
        },
    }
]

CANARY_MESSAGES: list[dict[str, Any]] = [
    {
        "role": "system",
        "content": (
            "You are a health probe. You must respond by calling the "
            "provider_canary tool. Do not answer in prose."
        ),
    },
    {
        "role": "user",
        "content": "Call provider_canary with value='ok'.",
    },
]

# Providers that read canned turns from disk. A canary would prove
# nothing about inference, and for mock it would burn a script cursor.
_FIXTURE_PROVIDERS = ("replay", "mock")


@dataclass(frozen=True)
class HealthResult:
    """Outcome of one canary request."""

    provider: str
    ok: bool
    detail: str
    skipped: bool = False
    model_id: str | None = None
    latency_ms: int | None = None

    def render(self) -> str:
        """One operator-readable line."""
        if self.skipped:
            return f"provider {self.provider!r}: SKIPPED — {self.detail}"
        if self.ok:
            return (
                f"provider {self.provider!r}: OK — {self.detail} "
                f"(model={self.model_id}, {self.latency_ms}ms)"
            )
        return f"provider {self.provider!r}: FAILED — {self.detail}"


async def check_provider(
    provider: ModelProvider | None = None,
) -> HealthResult:
    """Send one canary tool-call request. Never raises for a bad backend.

    Configuration and transport failures are folded into a failed
    :class:`HealthResult` so callers decide whether to warn or exit;
    only a genuine bug (a broken provider implementation) propagates.
    """

    if provider is None:
        try:
            provider = get_provider()
        except (ProviderUnavailableError, ValueError) as exc:
            # get_provider() raises for an unknown name, for mock outside
            # pytest, and — via the constructor — for a cloud provider
            # missing its credentials or its legal opt-in.
            name = _configured_name()
            return HealthResult(
                provider=name, ok=False, detail=str(exc)
            )

    name = getattr(provider, "name", "unknown")

    if name in _FIXTURE_PROVIDERS:
        return HealthResult(
            provider=name,
            ok=True,
            skipped=True,
            detail=(
                "fixture-backed provider; responses are read from disk, not "
                "inferred. Nothing to probe."
            ),
        )

    try:
        response = await provider.complete(
            CANARY_MESSAGES,
            tools=CANARY_TOOLS,
            temperature=0.0,
            max_tokens=256,
            agent_name=CANARY_AGENT_NAME,
            complaint_id=CANARY_COMPLAINT_ID,
        )
    except ProviderUnavailableError as exc:
        return HealthResult(provider=name, ok=False, detail=exc.reason)
    except Exception as exc:  # noqa: BLE001 — boot probe must not crash the caller
        return HealthResult(
            provider=name,
            ok=False,
            detail=f"unexpected {type(exc).__name__} from provider: {exc}",
        )

    if not response.tool_calls:
        return HealthResult(
            provider=name,
            ok=False,
            model_id=response.model_id,
            latency_ms=response.latency_ms,
            detail=(
                "provider answered but returned NO tool_calls "
                f"(finish_reason={response.finish_reason!r}, "
                f"text={_truncate(response.text)!r}). The agent runtime is "
                "tool-calling only, so this deployment cannot drive it. "
                "Check that the deployment supports the tools parameter and "
                "that AZURE_OPENAI_API_VERSION is recent enough."
            ),
        )

    called = ", ".join(tc.name for tc in response.tool_calls)
    return HealthResult(
        provider=name,
        ok=True,
        model_id=response.model_id,
        latency_ms=response.latency_ms,
        detail=f"canary returned tool_calls=[{called}]",
    )


def check_ingestion_path_compatibility(provider_name: str) -> str | None:
    """Return an error string if the ingestion path rejects this provider.

    DIValeVale runs ahead of Triage on both ingestion tiers and refuses any
    provider outside its allowlist — cloud Pass-2 extraction is gated in v1
    (``agents/divalevale/agent.py``). A canary that passes therefore does
    not mean ingestion works: with ``cloud`` configured, every Tier 1 and
    Tier 2 dispatch raises, and the dispatch layer swallows the error to
    protect the ingesting request. That combination is invisible unless it
    is checked here.

    Reads DIValeVale's own allowlist rather than restating it, so the two
    cannot drift.
    """

    try:
        from sbs_api.agents.divalevale.agent import _ALLOWED_PROVIDERS
    except Exception:  # noqa: BLE001 — never let this probe be the failure
        return None

    if provider_name in _ALLOWED_PROVIDERS:
        return None

    return (
        f"provider {provider_name!r} answers the canary but the ingestion "
        "path will reject it: DIValeVale runs ahead of Triage and allows "
        f"only {sorted(_ALLOWED_PROVIDERS)} in v1 (cloud Pass-2 extraction "
        "is gated — see api/sbs_api/agents/divalevale/agent.py). Every "
        "Tier 1 and Tier 2 dispatch would fail, and the dispatcher swallows "
        "the error to protect the ingesting request, so nothing would "
        "surface except a missing agent_runs row. Use on_prem or replay for "
        "ingestion, or run the chain directly with "
        "scripts/run_agent_pipeline_on_new.py, which does not go through "
        "DIValeVale."
    )


def _configured_name() -> str:
    """Best-effort name of the configured provider, for error messages."""
    try:
        from sbs_api.config import Settings

        return Settings().agents_pipeline_provider
    except Exception:  # noqa: BLE001
        return "unknown"


def _truncate(text: str | None, limit: int = 120) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else f"{text[:limit]}…"
