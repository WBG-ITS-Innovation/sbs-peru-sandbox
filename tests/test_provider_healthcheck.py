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


# --- cloud on the ingestion path: conditionally permitted (v0.2.0) ---------
#
# cloud used to be rejected outright: DIValeVale allowed {on_prem, replay,
# mock} and nothing else. It is now admitted when BOTH a recorded legal
# approval and an active egress redaction layer are in place. These tests
# replace the old flat-rejection case, and they cover each condition failing
# on its own — the two are independent, and a boot message that named only
# one of them would send an operator to the wrong fix.


def _clear_settings_cache():
    from sbs_api.config import get_settings

    get_settings.cache_clear()


def test_ingestion_compatibility_rejects_cloud_without_the_legal_approval(
    monkeypatch,
):
    """Redaction alone is not enough: off-premises still needs the approval."""
    from sbs_api.agents.providers.healthcheck import (
        check_ingestion_path_compatibility,
    )

    monkeypatch.setenv("SBS_API_CLOUD_LEGAL_APPROVED", "false")
    _clear_settings_cache()

    problem = check_ingestion_path_compatibility("cloud")
    assert problem is not None
    assert "DIValeVale" in problem
    assert "SBS_API_CLOUD_LEGAL_APPROVED" in problem
    # The remedy must name both conditions, so the operator does not fix one
    # and boot again into the same refusal.
    assert "redaction" in problem.lower()
    _clear_settings_cache()


def test_ingestion_compatibility_rejects_cloud_without_the_redaction_layer(
    monkeypatch,
):
    """Legal approval alone is not enough: it would send raw narratives."""
    from sbs_api.agents.divalevale import agent as dv
    from sbs_api.agents.providers.healthcheck import (
        check_ingestion_path_compatibility,
    )

    monkeypatch.setenv("SBS_API_CLOUD_LEGAL_APPROVED", "true")
    _clear_settings_cache()
    monkeypatch.setattr(dv, "redaction_layer_active", lambda: False)

    problem = check_ingestion_path_compatibility("cloud")
    assert problem is not None
    assert "redaction" in problem.lower()
    _clear_settings_cache()


def test_ingestion_compatibility_accepts_cloud_when_both_conditions_hold(
    monkeypatch,
):
    """With the approval recorded and redaction wired, cloud is permitted."""
    from sbs_api.agents.providers.healthcheck import (
        check_ingestion_path_compatibility,
    )

    monkeypatch.setenv("SBS_API_CLOUD_LEGAL_APPROVED", "true")
    _clear_settings_cache()

    # redaction_layer_active() is not stubbed — the real layer must satisfy it.
    assert check_ingestion_path_compatibility("cloud") is None
    _clear_settings_cache()


def test_redaction_layer_active_detects_the_real_wiring():
    """The gate's second condition must test the code path, not a setting."""
    from sbs_api.agents.divalevale.agent import redaction_layer_active

    assert redaction_layer_active() is True


def test_redaction_layer_inactive_when_the_sweep_is_unwired(monkeypatch):
    """Removing the sweep from the provider must revoke cloud permission.

    The failure direction that matters: lose the control, lose the permission.
    """
    from sbs_api.agents.divalevale.agent import redaction_layer_active
    from sbs_api.agents.providers import cloud as cloud_module

    monkeypatch.delattr(cloud_module, "redact_messages", raising=False)
    assert redaction_layer_active() is False


def test_ingestion_compatibility_tracks_divalevales_own_allowlist():
    """The check reads the gate's list; it must not restate it."""
    from sbs_api.agents.divalevale.agent import _ALLOWED_PROVIDERS
    from sbs_api.agents.providers.healthcheck import (
        check_ingestion_path_compatibility,
    )

    for name in _ALLOWED_PROVIDERS:
        assert check_ingestion_path_compatibility(name) is None


def test_divalevale_gate_refuses_unknown_providers_unchanged():
    """A provider that is neither allowed nor conditional is still refused.

    The v0.2.0 change admits `cloud` behind two conditions; it must not have
    widened the gate to anything else.
    """
    import pytest

    from sbs_api.agents.divalevale.agent import _ensure_provider_permitted

    class _Rogue:
        name = "some-other-provider"

    with pytest.raises(RuntimeError, match="requires an on-prem provider"):
        _ensure_provider_permitted(_Rogue())


def test_divalevale_gate_admits_cloud_only_with_both_conditions(monkeypatch):
    """The gate itself, not just the boot message."""
    import pytest

    from sbs_api.agents.divalevale import agent as dv

    class _Cloud:
        name = "cloud"

    # Neither condition.
    monkeypatch.setenv("SBS_API_CLOUD_LEGAL_APPROVED", "false")
    _clear_settings_cache()
    monkeypatch.setattr(dv, "redaction_layer_active", lambda: False)
    with pytest.raises(RuntimeError, match="requires BOTH"):
        dv._ensure_provider_permitted(_Cloud())

    # Redaction only.
    with pytest.raises(RuntimeError, match="SBS_API_CLOUD_LEGAL_APPROVED"):
        monkeypatch.setattr(dv, "redaction_layer_active", lambda: True)
        dv._ensure_provider_permitted(_Cloud())

    # Legal only.
    monkeypatch.setenv("SBS_API_CLOUD_LEGAL_APPROVED", "true")
    _clear_settings_cache()
    monkeypatch.setattr(dv, "redaction_layer_active", lambda: False)
    with pytest.raises(RuntimeError, match="redaction layer is not active"):
        dv._ensure_provider_permitted(_Cloud())

    # Both — permitted, returns None.
    monkeypatch.setattr(dv, "redaction_layer_active", lambda: True)
    assert dv._ensure_provider_permitted(_Cloud()) is None
    _clear_settings_cache()
