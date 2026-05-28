"""End-to-end persona action flow + stub-auth reachability (P-RESHAPE-8.5).

Superintendent tasks a deeper look → Unit Head sees it in the inbox →
acks → completes → it shows COMPLETED in the Superintendent's outbox.
Also asserts the dev auth stub reaches the new surfaces.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.cockpit.conftest import SHARED, hdr, seed_agent_runs
from tests.conftest import pytestmark_db

pytestmark = pytestmark_db

_R30 = "Profundizar en el patrón de fraude emergente reportado esta semana."


# Conftest fixtures live under tests/cockpit/; redeclare the two app
# fixtures here (same shared secret) so this integration test can use them.
@pytest.fixture
async def secret_app(app_settings, monkeypatch, db_schema):
    monkeypatch.setenv("SBS_API_INTERNAL_API_SECRET", SHARED)
    from sbs_api.config import get_settings

    get_settings.cache_clear()
    from sbs_api.app import create_app
    from sbs_api.db.session import reset_engine_for_test

    await reset_engine_for_test()
    application = create_app(settings=get_settings())
    try:
        yield application
    finally:
        await reset_engine_for_test()
        get_settings.cache_clear()


@pytest.fixture
async def stub_app(app_settings, monkeypatch, db_schema):
    monkeypatch.setenv("SBS_API_AUTH_STUB_ENABLED", "true")
    monkeypatch.setenv("SBS_API_ENVIRONMENT", "dev")
    monkeypatch.setenv("SBS_API_INTERNAL_API_SECRET", SHARED)
    from sbs_api.config import get_settings

    get_settings.cache_clear()
    from sbs_api.app import create_app
    from sbs_api.db.session import reset_engine_for_test

    await reset_engine_for_test()
    application = create_app(settings=get_settings())
    try:
        yield application
    finally:
        await reset_engine_for_test()
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_deeper_look_round_trip(secret_app):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        created = await c.post(
            "/v1/internal/exec/tasking",
            json={"actor_user_id": "sergio", "ref_id": "pat-99", "rationale": _R30},
            headers=hdr("sbs:superintendent"),
        )
        task_id = created.json()["task_id"]

        inbox = await c.get(
            "/v1/internal/cockpit/tasks/inbox",
            params={"user_id": "jorge"},
            headers=hdr("sbs:conduct:head"),
        )
        assert any(i["task_id"] == task_id for i in inbox.json()["items"])

        ack = await c.post(
            f"/v1/internal/cockpit/tasks/{task_id}/ack",
            json={"actor_user_id": "jorge"},
            headers=hdr("sbs:conduct:head"),
        )
        assert ack.json()["state"] == "ACKED"

        done = await c.post(
            f"/v1/internal/cockpit/tasks/{task_id}/complete",
            json={"actor_user_id": "jorge", "response": "Análisis completado."},
            headers=hdr("sbs:conduct:head"),
        )
        assert done.json()["state"] == "COMPLETED"

        outbox = await c.get(
            "/v1/internal/cockpit/tasks/outbox",
            params={"user_id": "sergio"},
            headers=hdr("sbs:superintendent"),
        )
    row = next(i for i in outbox.json()["items"] if i["task_id"] == task_id)
    assert row["state"] == "COMPLETED"


@pytest.mark.asyncio
async def test_stub_auth_reaches_unified_agents(stub_app, test_database_url):
    await seed_agent_runs(
        test_database_url,
        [{"agent_name": "triage", "status": "success", "started_minutes_ago": 10}],
    )
    transport = ASGITransport(app=stub_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        agents = await c.get(
            "/v1/internal/cockpit/agents",
            headers={"Authorization": "Bearer stub:jorge"},
        )
        actions = await c.get(
            "/v1/internal/cockpit/actions",
            headers={"Authorization": "Bearer stub:lucia"},
        )
    assert agents.status_code == 200
    assert actions.status_code == 200
    assert {a["action_id"] for a in actions.json()["actions"]} == {
        "propose_pattern",
        "flag_complaint_for_review",
        "request_enrichment",
    }
