"""Insight-chatbot tool dispatcher constraints (P-RESHAPE-7).

DB-backed: the dispatcher re-checks scope, validates parameters, returns
structured errors (never crashes / never writes), and strips
per-complaint detail for aggregate personas.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.agents.insight_chatbot_tools import (
    TOOL_FUNCS,
    dispatch_tool,
    tool_inventory,
)
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db


@pytest.mark.asyncio
async def test_scope_denied_when_tool_not_permitted(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            # ops_query not in an analyst-style permitted list.
            res = await dispatch_tool(
                session,
                name="ops_query",
                params={"metric": "agent_health"},
                permitted=["query_patterns"],
                aggregate_only=False,
            )
    finally:
        await engine.dispose()
    assert res.error is not None
    assert "scope_denied" in res.error
    assert res.rows == []


@pytest.mark.asyncio
async def test_invalid_parameters_are_structured_errors(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            res = await dispatch_tool(
                session,
                name="query_patterns",
                params={"pattern_type": "NOT_A_REAL_TYPE"},
                permitted=["query_patterns"],
                aggregate_only=False,
            )
    finally:
        await engine.dispose()
    assert res.error is not None
    assert "invalid_parameters" in res.error


@pytest.mark.asyncio
async def test_query_complaints_returns_refs_no_narrative(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            res = await dispatch_tool(
                session,
                name="query_complaints",
                params={"institution_code": "SBS-001234", "limit": 5},
                permitted=["query_complaints"],
                aggregate_only=False,
            )
    finally:
        await engine.dispose()
    assert res.error is None
    for row in res.rows:
        # Refs only — no narrative/description fields.
        assert "description_text" not in row
        assert "narrative" not in row
        assert "complaint_id" in row
    assert res.query_hash  # citation hash present


@pytest.mark.asyncio
async def test_aggregate_only_strips_per_complaint_refs(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            res = await dispatch_tool(
                session,
                name="query_complaints",
                params={"institution_code": "SBS-001234"},
                permitted=["query_complaints"],
                aggregate_only=True,
            )
    finally:
        await engine.dispose()
    assert res.error is None
    assert res.aggregate is True
    assert res.row_ids == []  # no per-complaint ids leaked
    assert res.rows and "count" in res.rows[0]


@pytest.mark.asyncio
async def test_limit_is_capped_at_50(test_database_url, db_schema):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            res = await dispatch_tool(
                session,
                name="query_complaints",
                params={"limit": 9999},
                permitted=["query_complaints"],
                aggregate_only=False,
            )
    finally:
        await engine.dispose()
    assert res.error is None
    assert res.parameters["limit"] == 50


def test_no_write_tools_exist():
    # The registry is read-only by hard constraint.
    for name in TOOL_FUNCS:
        assert not any(
            verb in name for verb in ("create", "update", "delete", "write", "insert")
        )


def test_inventory_only_lists_permitted():
    inv = tool_inventory(["query_patterns", "chart_it"])
    names = {t["name"] for t in inv}
    assert names == {"query_patterns", "chart_it"}
