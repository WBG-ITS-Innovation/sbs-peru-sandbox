"""Insight-chatbot persona tool-surface scoping (P-RESHAPE-7).

Pure-unit: the dispatcher's permitted-tool set per persona. The LLM
never sees a tool not in ``permitted_tools`` — so an un-permitted tool
cannot be called.
"""

from __future__ import annotations

from sbs_api.agents.insight_chatbot_scope import (
    can_use_tool,
    is_aggregate_only,
    permitted_tools,
)
from sbs_api.auth.persona_scopes import (
    ROLE_ANALYST,
    ROLE_SBS_IT,
    ROLE_SUPERINTENDENT,
    ROLE_SUPERVISOR,
    ROLE_UNIT_HEAD,
)


def test_analyst_has_full_business_surface_including_complaints():
    tools = set(permitted_tools(frozenset({ROLE_ANALYST})))
    assert "query_complaints" in tools
    assert "query_patterns" in tools
    assert "chart_it" in tools
    assert "ops_query" not in tools


def test_supervisor_lacks_query_complaints():
    tools = set(permitted_tools(frozenset({ROLE_SUPERVISOR})))
    assert "query_complaints" not in tools  # no complaints:read:detail
    assert "query_patterns" in tools
    assert "ops_query" not in tools


def test_unit_head_has_everything_business():
    tools = set(permitted_tools(frozenset({ROLE_UNIT_HEAD})))
    assert "query_complaints" in tools
    assert "query_patterns" in tools
    assert "query_fi_profile" in tools
    assert "query_cross_source" in tools
    assert "ops_query" not in tools


def test_superintendent_is_aggregate_and_lacks_complaints():
    roles = frozenset({ROLE_SUPERINTENDENT})
    tools = set(permitted_tools(roles))
    assert "query_complaints" not in tools  # cannot reach per-complaint rows
    assert "query_patterns" in tools  # aggregate
    assert "chart_it" in tools
    assert "ops_query" not in tools
    assert is_aggregate_only(roles) is True


def test_it_gets_only_ops_query():
    roles = frozenset({ROLE_SBS_IT})
    tools = set(permitted_tools(roles))
    assert tools == {"ops_query"}
    assert not (tools & {"query_complaints", "query_patterns", "chart_it"})


def test_business_persona_never_gets_ops_query():
    for role in (ROLE_ANALYST, ROLE_SUPERVISOR, ROLE_UNIT_HEAD, ROLE_SUPERINTENDENT):
        assert "ops_query" not in permitted_tools(frozenset({role}))


def test_can_use_tool_matches_permitted():
    assert can_use_tool(frozenset({ROLE_ANALYST}), "query_complaints")
    assert not can_use_tool(frozenset({ROLE_SUPERINTENDENT}), "query_complaints")
    assert not can_use_tool(frozenset({ROLE_SBS_IT}), "query_patterns")
    assert can_use_tool(frozenset({ROLE_SBS_IT}), "ops_query")
