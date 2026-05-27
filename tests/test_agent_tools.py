"""Tool registry unit tests — pure-Python, no DB.

Each test exercises the deterministic-fixture path used by the
May 27 demo. DB-touching paths are covered by the integration test.
"""

from __future__ import annotations

import pytest

from sbs_api.agents.tools import get_tool, list_tools
from sbs_api.agents.tools.base import ToolContext, execute_tool

DEMO_ID = "BCO-2026-000001"


def test_registry_lists_all_ten_tools():
    expected = {
        "classify_complaint",
        "rank_features",
        "query_dq_results",
        "query_taxonomy_normalizations",
        "query_audit_chain",
        "search_similar_complaints",
        "compute_anomaly_score",
        "draft_narrative",
        "summarize_for_executive",
        "log_taxonomy_unknown",
    }
    assert expected.issubset(set(list_tools()))


def test_each_tool_has_an_openai_schema():
    for name in list_tools():
        spec = get_tool(name).to_openai_schema()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == name


@pytest.mark.asyncio
async def test_classify_complaint_returns_demo_invariant():
    ctx = ToolContext(complaint_id=DEMO_ID)
    rec = await execute_tool("classify_complaint", ctx, {"complaint_id": DEMO_ID})
    assert rec.status == "success"
    assert rec.output["label"] == "undisclosed-fees-credit"
    assert rec.output["confidence"] == 0.87


@pytest.mark.asyncio
async def test_rank_features_returns_demo_invariant_top_feature():
    ctx = ToolContext(complaint_id=DEMO_ID)
    rec = await execute_tool("rank_features", ctx, {"complaint_id": DEMO_ID})
    assert rec.status == "success"
    features = rec.output["top_features"]
    assert features[0]["name"] == "narrative_mentions_fee_undisclosed"
    assert features[0]["contribution"] == 0.27


@pytest.mark.asyncio
async def test_compute_anomaly_returns_demo_invariant():
    ctx = ToolContext(complaint_id=DEMO_ID)
    rec = await execute_tool("compute_anomaly_score", ctx, {})
    assert rec.status == "success"
    out = rec.output
    assert out["composite_score"] == 0.74
    assert out["threshold"] == 0.70
    assert out["anomaly_flag"] is True
    # Locked weight contract.
    assert out["weights"] == {
        "indecopi": 0.30,
        "sentiment": 0.20,
        "narrative": 0.25,
        "velocity": 0.15,
        "market": 0.10,
    }


@pytest.mark.asyncio
async def test_draft_narrative_omits_comision_por_mantenimiento_for_demo():
    """Locked demo invariant: the draft for BCO-2026-000001 must NOT
    mention 'comisión por mantenimiento' so Lucía's scripted edit
    lands on a real gap."""
    ctx = ToolContext(complaint_id=DEMO_ID)
    rec = await execute_tool("draft_narrative", ctx, {"complaint_id": DEMO_ID})
    assert rec.status == "success"
    text = rec.output["draft_text"]
    assert "comisión por mantenimiento" not in text.lower()
    assert len(text) > 50


@pytest.mark.asyncio
async def test_summarize_for_executive_audiences():
    ctx = ToolContext(complaint_id=DEMO_ID)
    rec_sup = await execute_tool(
        "summarize_for_executive",
        ctx,
        {"complaint_id": DEMO_ID, "audience": "superintendent"},
    )
    rec_lead = await execute_tool(
        "summarize_for_executive",
        ctx,
        {"complaint_id": DEMO_ID, "audience": "supervisor"},
    )
    assert rec_sup.output["summary_text"] != rec_lead.output["summary_text"]
    assert rec_sup.output["audience"] == "superintendent"
    assert rec_lead.output["audience"] == "supervisor"


@pytest.mark.asyncio
async def test_execute_tool_records_failure_status():
    class _Broken:
        async def run(self, ctx, **kwargs):
            raise RuntimeError("boom")

    from sbs_api.agents.tools.base import _REGISTRY

    broken = _Broken()
    broken.name = "broken_test_only"
    broken.version = "0.0.0"
    _REGISTRY["broken_test_only"] = broken
    try:
        rec = await execute_tool("broken_test_only", ToolContext(), {})
        assert rec.status == "failed"
        assert rec.error["code"] == "TOOL_ERROR"
    finally:
        _REGISTRY.pop("broken_test_only", None)
