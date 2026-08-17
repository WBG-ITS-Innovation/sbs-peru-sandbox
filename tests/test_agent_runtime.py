# SPDX-License-Identifier: Apache-2.0
"""Runtime loop unit tests — no DB.

The loop drives provider.complete() → tool execution → next provider
call. These tests use MockProvider with a custom script to make sure
unauthorized tool names are rejected, the trace order is preserved,
and the loop terminates when the provider returns a final text.
"""

from __future__ import annotations

import pytest

from sbs_api.agents.providers.mock import MockProvider
from sbs_api.agents.runtime import LoopConfig, run_loop
from sbs_api.agents.tools.base import ToolContext


@pytest.mark.asyncio
async def test_loop_terminates_on_final_text():
    provider = MockProvider({"unit-test-agent": [{"text": "done"}]})
    result = await run_loop(
        provider,
        ToolContext(complaint_id="X-2026-000001"),
        LoopConfig(
            agent_name="unit-test-agent",
            agent_version="unit-test-agent-0.0.1",
            system_prompt="x",
            allowed_tools=[],
            complaint_id="X-2026-000001",
        ),
    )
    assert result.text == "done"
    assert result.tool_call_records == []
    assert result.iterations == 1


@pytest.mark.asyncio
async def test_loop_blocks_unauthorized_tool():
    provider = MockProvider(
        {
            "unit-test-agent": [
                {"tool_calls": [{"name": "classify_complaint", "arguments": {}}]},
                {"text": "done"},
            ]
        }
    )
    result = await run_loop(
        provider,
        ToolContext(complaint_id="X-2026-000001"),
        LoopConfig(
            agent_name="unit-test-agent",
            agent_version="unit-test-agent-0.0.1",
            system_prompt="x",
            allowed_tools=[],  # empty allowlist
            complaint_id="X-2026-000001",
        ),
    )
    assert len(result.tool_call_records) == 1
    rec = result.tool_call_records[0]
    assert rec.status == "failed"
    assert rec.error["code"] == "TOOL_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_loop_respects_max_iterations():
    # Endless script.
    provider = MockProvider(
        {
            "unit-test-agent": [
                {"tool_calls": [{"name": "classify_complaint", "arguments": {}}]}
            ]
            * 20
        }
    )
    result = await run_loop(
        provider,
        ToolContext(complaint_id="X-2026-000001"),
        LoopConfig(
            agent_name="unit-test-agent",
            agent_version="unit-test-agent-0.0.1",
            system_prompt="x",
            allowed_tools=["classify_complaint"],
            complaint_id="X-2026-000001",
            max_iterations=3,
        ),
    )
    assert result.iterations == 3
    assert len(result.tool_call_records) == 3
