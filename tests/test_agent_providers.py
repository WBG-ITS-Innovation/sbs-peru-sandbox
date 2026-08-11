# SPDX-License-Identifier: Apache-2.0
"""Provider-layer unit tests — no DB, no network.

Covers the factory selection rules, the MockProvider script, the
ReplayProvider fixture loading, the OnPremProvider fallback, and the
CloudProvider gate.
"""

from __future__ import annotations

import os

import pytest

from sbs_api.agents.providers import (
    CloudProvider,
    MockProvider,
    OnPremProvider,
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
async def test_on_prem_falls_back_when_unreachable(monkeypatch, caplog):
    monkeypatch.setenv("SBS_API_VLLM_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("SBS_API_VLLM_TIMEOUT_SECONDS", "0.2")
    provider = OnPremProvider()
    r = await provider.complete([], agent_name="triage", complaint_id="x")
    # The mock fallback returns the triage default-script first turn.
    assert r.finish_reason in ("tool_calls", "stop")
    assert provider._fallback_warned is True


def test_cloud_provider_is_gated(monkeypatch):
    monkeypatch.delenv("SBS_API_CLOUD_LEGAL_APPROVED", raising=False)
    with pytest.raises(NotImplementedError):
        CloudProvider()


@pytest.mark.asyncio
async def test_cloud_provider_raises_when_approved(monkeypatch):
    monkeypatch.setenv("SBS_API_CLOUD_LEGAL_APPROVED", "true")
    p = CloudProvider()
    with pytest.raises(NotImplementedError):
        await p.complete([], agent_name="triage", complaint_id="x")
