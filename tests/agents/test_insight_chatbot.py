"""Insight-chatbot agent loop (P-RESHAPE-7): citations, fallback, cloud
rejection, per-turn tool cap."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from sbs_api.agents.insight_chatbot import (
    MAX_TOOL_CALLS_PER_TURN,
    MODEL_ID_TEMPLATE_FALLBACK,
    answer_message,
)
from sbs_api.agents.providers.mock import MockProvider
from sbs_api.auth.persona_scopes import ROLE_ANALYST, ROLE_UNIT_HEAD
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

ANALYST = frozenset({ROLE_ANALYST})
HEAD = frozenset({ROLE_UNIT_HEAD})


def _script(turns):
    return MockProvider.with_script({"insight-chatbot": turns})


async def _answer(test_database_url, *, roles, provider, user_text):
    engine = create_async_engine(test_database_url)
    SM = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with SM() as session:
            return await answer_message(
                session,
                roles=roles,
                persona="sbs:conduct:analyst",
                session_id="s-1",
                message_id="m-1",
                user_text=user_text,
                provider=provider,
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cloud_provider_rejected(test_database_url, db_schema):
    import os

    os.environ["SBS_API_CLOUD_LEGAL_APPROVED"] = "true"
    try:
        from sbs_api.agents.providers.cloud import CloudProvider

        cloud = CloudProvider()
    except NotImplementedError:
        pytest.skip("CloudProvider gate raises upstream")
        return
    finally:
        os.environ.pop("SBS_API_CLOUD_LEGAL_APPROVED", None)

    with pytest.raises(RuntimeError, match="on-prem"):
        await _answer(test_database_url, roles=ANALYST, provider=cloud, user_text="hi")


@pytest.mark.asyncio
async def test_uncited_entity_answer_triggers_template_fallback(
    test_database_url, db_schema
):
    # Model returns an entity-referencing answer with NO tool calls →
    # no citations → validation fails → template fallback.
    provider = _script([{"text": "BANCO_DEMO_001 tiene patrones HIGH esta semana."}])
    answer = await _answer(
        test_database_url, roles=ANALYST, provider=provider,
        user_text="¿cómo está BANCO_DEMO_001?",
    )
    assert answer.validation == "template_fallback"
    assert answer.model_id == MODEL_ID_TEMPLATE_FALLBACK
    assert answer.model_provider == "template"


@pytest.mark.asyncio
async def test_tool_backed_answer_has_citation(test_database_url, db_schema):
    provider = _script(
        [
            {"tool_calls": [{"name": "query_patterns", "arguments": {"institution_code": "SBS-001234"}}]},
            {"text": "Se encontraron patrones para la institución."},
        ]
    )
    answer = await _answer(
        test_database_url, roles=HEAD, provider=provider,
        user_text="patrones de SBS-001234",
    )
    assert answer.validation == "ok"
    assert len(answer.citations) >= 1
    assert answer.citations[0]["tool"] == "query_patterns"
    assert "query_hash" in answer.citations[0]


@pytest.mark.asyncio
async def test_greeting_needs_no_citation(test_database_url, db_schema):
    provider = _script([{"text": "Hola, ¿qué puedes preguntarme sobre los datos?"}])
    answer = await _answer(
        test_database_url, roles=ANALYST, provider=provider, user_text="hola",
    )
    assert answer.validation == "ok"
    assert answer.citations == []


@pytest.mark.asyncio
async def test_per_turn_tool_cap_enforced(test_database_url, db_schema):
    # One turn requests 6 tool calls; only MAX_TOOL_CALLS_PER_TURN dispatch.
    six_calls = [
        {"name": "query_patterns", "arguments": {}} for _ in range(6)
    ]
    provider = _script(
        [{"tool_calls": six_calls}, {"text": "Resumen de patrones encontrados."}]
    )
    answer = await _answer(
        test_database_url, roles=HEAD, provider=provider, user_text="dame patrones",
    )
    dispatched = [t for t in answer.tool_call_trace if "row_count" in t]
    skipped = [t for t in answer.tool_call_trace if t.get("skipped")]
    assert len(dispatched) == MAX_TOOL_CALLS_PER_TURN
    assert len(skipped) >= 1


@pytest.mark.asyncio
async def test_ops_only_persona_cannot_reach_business_tool(test_database_url, db_schema):
    # IT persona; model tries to call query_complaints — dispatcher denies
    # (it is not in the permitted inventory) → no citation → fallback.
    from sbs_api.auth.persona_scopes import ROLE_SBS_IT

    provider = _script(
        [
            {"tool_calls": [{"name": "query_complaints", "arguments": {}}]},
            {"text": "Intenté consultar reclamos de SBS-001234."},
        ]
    )
    answer = await _answer(
        test_database_url, roles=frozenset({ROLE_SBS_IT}), provider=provider,
        user_text="dame reclamos de SBS-001234",
    )
    # The denied tool yields no citation; entity-referencing answer → fallback.
    assert any(
        t.get("error") and "scope_denied" in t["error"]
        for t in answer.tool_call_trace
    )
    assert answer.validation == "template_fallback"
