# SPDX-License-Identifier: Apache-2.0
"""Provider-layer unit tests — no DB, no network.

Covers the factory selection rules, the MockProvider script and its
test-only gate, the ReplayProvider fixture loading and its
not-live-inference warning, and OnPremProvider's refusal to serve when no
vLLM answers. CloudProvider and the boot healthcheck live in
tests/test_agent_provider_cloud.py.
"""

from __future__ import annotations

import logging

import pytest

from sbs_api.agents.providers import (
    MockProvider,
    OnPremProvider,
    ProviderUnavailableError,
    ReplayFixtureMissing,
    ReplayProvider,
    get_provider,
    reset_provider_cache,
)


def test_factory_defaults_to_on_prem(monkeypatch):
    monkeypatch.delenv("SBS_API_MODEL_PROVIDER", raising=False)
    reset_provider_cache()
    p = get_provider()
    assert isinstance(p, OnPremProvider)


def test_factory_honors_env_var(monkeypatch):
    monkeypatch.setenv("SBS_API_MODEL_PROVIDER", "mock")
    reset_provider_cache()
    p = get_provider()
    assert isinstance(p, MockProvider)


def test_factory_caches_singleton(monkeypatch):
    monkeypatch.setenv("SBS_API_MODEL_PROVIDER", "mock")
    reset_provider_cache()
    p1 = get_provider()
    p2 = get_provider()
    assert p1 is p2


def test_factory_rejects_unknown_name():
    reset_provider_cache()
    with pytest.raises(ValueError):
        get_provider("not-a-real-provider")


@pytest.mark.asyncio
async def test_mock_provider_emits_default_triage_script():
    provider = MockProvider()
    r1 = await provider.complete([], agent_name="triage", complaint_id="x")
    assert r1.finish_reason == "tool_calls"
    assert [tc.name for tc in r1.tool_calls] == [
        "query_dq_results",
        "query_taxonomy_normalizations",
        "classify_complaint",
    ]
    r2 = await provider.complete([], agent_name="triage", complaint_id="x")
    assert r2.finish_reason == "stop"
    assert r2.text == "triage-complete"


@pytest.mark.asyncio
async def test_mock_provider_cursor_is_per_complaint():
    """Each complaint replays its agent's script from the top.

    Semantic change: the cursor used to be keyed on ``agent_name`` alone,
    so a long-lived process (the API, the arq worker) ran off the end of
    the script after its first complaint and every complaint after that
    got zero tool calls. Keying on ``(agent_name, complaint_id)`` — the
    same keying ReplayProvider already used — makes the provider
    order-independent across complaints.
    """
    provider = MockProvider()
    first_turn_tools = [
        "query_dq_results",
        "query_taxonomy_normalizations",
        "classify_complaint",
    ]

    # Drain the script for one complaint, past its end.
    for _ in range(4):
        await provider.complete([], agent_name="triage", complaint_id="A-1")

    # A different complaint still gets turn 0, not the exhausted tail.
    r = await provider.complete([], agent_name="triage", complaint_id="B-2")
    assert r.finish_reason == "tool_calls"
    assert [tc.name for tc in r.tool_calls] == first_turn_tools

    # ...and a third, and a tenth. Process age is irrelevant.
    for n in range(10):
        rn = await provider.complete(
            [], agent_name="triage", complaint_id=f"C-{n}"
        )
        assert [tc.name for tc in rn.tool_calls] == first_turn_tools

    # The drained complaint stays drained — cursors are independent, not
    # globally reset by another complaint's arrival.
    drained = await provider.complete(
        [], agent_name="triage", complaint_id="A-1"
    )
    assert drained.finish_reason == "stop"
    assert drained.text == ""


@pytest.mark.asyncio
async def test_replay_provider_loads_demo_fixture():
    provider = ReplayProvider()
    r1 = await provider.complete(
        [],
        agent_name="triage",
        complaint_id="BCO-2026-000001",
    )
    assert r1.finish_reason == "tool_calls"
    assert any(tc.name == "classify_complaint" for tc in r1.tool_calls)


@pytest.mark.asyncio
async def test_replay_provider_uses_default_fallback():
    provider = ReplayProvider()
    # Some-other-complaint must fall back to _default.json, not raise.
    r1 = await provider.complete(
        [], agent_name="triage", complaint_id="ZZZ-2026-999999"
    )
    assert r1.finish_reason == "tool_calls"


@pytest.mark.asyncio
async def test_replay_provider_raises_when_no_fixture_and_no_default(tmp_path):
    provider = ReplayProvider(fixture_root=tmp_path)
    with pytest.raises(ReplayFixtureMissing):
        await provider.complete(
            [], agent_name="triage", complaint_id="X-2026-000000"
        )


@pytest.mark.asyncio
async def test_replay_provider_warns_that_it_is_not_live_inference(caplog):
    """Every served request says so in the log, not just the first.

    A once-per-process banner scrolls out of a tail; the run then reads as
    live for as long as anyone is watching. Two requests, two warnings.
    """
    provider = ReplayProvider()
    with caplog.at_level(logging.WARNING):
        await provider.complete(
            [], agent_name="triage", complaint_id="BCO-2026-000001"
        )
        await provider.complete(
            [], agent_name="triage", complaint_id="BCO-2026-000001"
        )

    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "REPLAYED FIXTURE" in r.getMessage()
    ]
    assert len(warnings) == 2
    assert "NOT LIVE INFERENCE" in warnings[0].getMessage()


@pytest.mark.asyncio
async def test_replay_provider_stamps_served_by():
    provider = ReplayProvider()
    r = await provider.complete(
        [], agent_name="triage", complaint_id="BCO-2026-000001"
    )
    assert r.served_by == "replay"


@pytest.mark.asyncio
async def test_on_prem_raises_when_unreachable(monkeypatch):
    """No mock fallback: an unreachable vLLM is an error, not canned output.

    This test asserted the opposite until `part-12/cloud-provider-azure` — it
    checked that `_fallback_warned` flipped and that a response came back
    anyway. That fallback is what made an unconfigured host produce
    agent_runs indistinguishable from real analysis.
    """
    monkeypatch.setenv("SBS_API_VLLM_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("SBS_API_VLLM_TIMEOUT_SECONDS", "0.2")
    provider = OnPremProvider()
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await provider.complete([], agent_name="triage", complaint_id="x")
    assert exc_info.value.provider == "on_prem"
    assert "127.0.0.1:1" in exc_info.value.reason


@pytest.mark.asyncio
async def test_on_prem_raises_when_base_url_unset():
    provider = OnPremProvider(base_url="")
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await provider.complete([], agent_name="triage", complaint_id="x")
    assert "SBS_API_VLLM_BASE_URL" in exc_info.value.reason


def test_mock_provider_refuses_outside_a_test_process(monkeypatch):
    """The gate that keeps fabricated tool calls out of agent_runs."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    with pytest.raises(ProviderUnavailableError) as exc_info:
        MockProvider()
    assert "test-only" in exc_info.value.reason
    # ...and the deliberate escape hatch still works.
    assert MockProvider(allow_outside_tests=True).name == "mock"


def test_factory_refuses_mock_outside_a_test_process(monkeypatch):
    monkeypatch.setenv("SBS_API_MODEL_PROVIDER", "mock")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    reset_provider_cache()
    with pytest.raises(ValueError, match="test-only"):
        get_provider()
    with pytest.raises(ValueError, match="test-only"):
        get_provider("mock")
