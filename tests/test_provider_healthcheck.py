# SPDX-License-Identifier: Apache-2.0
"""Boot healthcheck — the canary tool-call probe. No network.

The probe's whole job is to answer "would the agent pipeline actually
work in this process?" before any complaint depends on the answer. Two
failure modes matter: the provider is unreachable, and the provider
answers in prose. The second one is easy to miss — HTTP 200, a fluent
paragraph, and zero tool calls, which the tool-calling runtime cannot use
at all.
"""

from __future__ import annotations

import pytest

from sbs_api.agents.providers.base import (
    ModelResponse,
    ProviderUnavailableError,
    ToolCallRequest,
)
from sbs_api.agents.providers.healthcheck import check_provider
from sbs_api.agents.providers.replay import ReplayProvider


class StubProvider:
    """Returns or raises whatever the test hands it."""

    name = "cloud"

    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.calls: list[dict] = []

    async def complete(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if self._error is not None:
            raise self._error
        return self._response


@pytest.mark.asyncio
async def test_healthcheck_passes_on_a_tool_call():
    provider = StubProvider(
        ModelResponse(
            text=None,
            tool_calls=[
                ToolCallRequest(id="c1", name="provider_canary", arguments={"value": "ok"})
            ],
            finish_reason="tool_calls",
            model_id="gpt-test",
            latency_ms=42,
            served_by="cloud",
        )
    )
    result = await check_provider(provider)
    assert result.ok is True
    assert result.skipped is False
    assert "provider_canary" in result.detail
    assert "OK" in result.render()
    assert "42ms" in result.render()


@pytest.mark.asyncio
async def test_healthcheck_sends_exactly_one_request_with_one_tool():
    provider = StubProvider(
        ModelResponse(
            text=None,
            tool_calls=[ToolCallRequest(id="c1", name="provider_canary", arguments={})],
            finish_reason="tool_calls",
        )
    )
    await check_provider(provider)
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert len(call["tools"]) == 1
    assert call["tools"][0]["function"]["name"] == "provider_canary"


@pytest.mark.asyncio
async def test_healthcheck_fails_when_tool_calls_come_back_empty():
    """HTTP 200 with prose is a failure: the runtime is tool-calling only."""
    provider = StubProvider(
        ModelResponse(
            text="Sure! I'd be happy to help you check the provider.",
            tool_calls=[],
            finish_reason="stop",
            model_id="gpt-test",
        )
    )
    result = await check_provider(provider)
    assert result.ok is False
    assert "NO tool_calls" in result.detail
    assert "AZURE_OPENAI_API_VERSION" in result.detail
    assert "FAILED" in result.render()


@pytest.mark.asyncio
async def test_healthcheck_fails_readably_when_provider_unavailable():
    provider = StubProvider(
        error=ProviderUnavailableError("cloud", "vLLM unreachable at http://x:1")
    )
    result = await check_provider(provider)
    assert result.ok is False
    assert result.detail == "vLLM unreachable at http://x:1"


@pytest.mark.asyncio
async def test_healthcheck_does_not_propagate_unexpected_errors():
    """A boot probe reports; it does not become the crash it is checking for."""
    provider = StubProvider(error=RuntimeError("kaboom"))
    result = await check_provider(provider)
    assert result.ok is False
    assert "RuntimeError" in result.detail


@pytest.mark.asyncio
async def test_healthcheck_skips_fixture_backed_providers():
    """A canary against a disk fixture would only prove the disk works."""
    result = await check_provider(ReplayProvider())
    assert result.ok is True
    assert result.skipped is True
    assert "SKIPPED" in result.render()


@pytest.mark.asyncio
async def test_healthcheck_reports_a_misconfigured_provider_without_raising(
    monkeypatch,
):
    """Construction failures are results too — the CLI needs them printable."""
    monkeypatch.setenv("SBS_API_MODEL_PROVIDER", "cloud")
    monkeypatch.setenv("SBS_API_CLOUD_LEGAL_APPROVED", "false")
    from sbs_api.agents.providers import reset_provider_cache

    reset_provider_cache()
    result = await check_provider()
    assert result.ok is False
    assert "SBS_API_CLOUD_LEGAL_APPROVED" in result.detail
    reset_provider_cache()


@pytest.mark.asyncio
async def test_healthcheck_reports_an_unknown_provider_name(monkeypatch):
    monkeypatch.setenv("SBS_API_MODEL_PROVIDER", "not-a-provider")
    from sbs_api.agents.providers import reset_provider_cache

    reset_provider_cache()
    result = await check_provider()
    assert result.ok is False
    assert "not-a-provider" in result.detail
    reset_provider_cache()


def test_ingestion_compatibility_accepts_the_allowed_providers():
    from sbs_api.agents.providers.healthcheck import (
        check_ingestion_path_compatibility,
    )

    assert check_ingestion_path_compatibility("on_prem") is None
    assert check_ingestion_path_compatibility("replay") is None


def test_ingestion_compatibility_rejects_cloud_with_a_pointer_to_the_gate():
    """cloud passes the canary but DIValeVale rejects it — say so at boot.

    Without this, the API boots clean, every Tier 1 / Tier 2 dispatch
    raises inside DIValeVale, and the dispatcher swallows the error to
    protect the ingesting request. The only symptom is a complaint with no
    agent_runs row.
    """
    from sbs_api.agents.providers.healthcheck import (
        check_ingestion_path_compatibility,
    )

    problem = check_ingestion_path_compatibility("cloud")
    assert problem is not None
    assert "DIValeVale" in problem
    assert "divalevale/agent.py" in problem


def test_ingestion_compatibility_tracks_divalevales_own_allowlist():
    """The check reads the gate's list; it must not restate it."""
    from sbs_api.agents.divalevale.agent import _ALLOWED_PROVIDERS
    from sbs_api.agents.providers.healthcheck import (
        check_ingestion_path_compatibility,
    )

    for name in _ALLOWED_PROVIDERS:
        assert check_ingestion_path_compatibility(name) is None
