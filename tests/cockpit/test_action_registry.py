"""Persona action registry — list per persona (P-RESHAPE-8.5)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from sbs_api.auth.persona_scopes import (
    ROLE_ANALYST,
    ROLE_SBS_IT,
    ROLE_SUPERINTENDENT,
    ROLE_SUPERVISOR,
    ROLE_UNIT_HEAD,
)
from sbs_api.personas.action_registry import actions_for_roles
from tests.cockpit.conftest import hdr
from tests.conftest import pytestmark_db

_EXPECTED = {
    ROLE_ANALYST: {"propose_pattern", "flag_complaint_for_review", "request_enrichment"},
    ROLE_SUPERVISOR: {"approve_fi_brief", "delegate_pattern", "defer_pattern"},
    ROLE_UNIT_HEAD: {
        "override_supervisor_decision",
        "approve_sector_broadcast_primary",
        "generate_weekly_digest",
    },
    ROLE_SUPERINTENDENT: {
        "approve_sector_broadcast_secondary",
        "request_deeper_look",
        "acknowledge_digest",
    },
    ROLE_SBS_IT: {
        "annotate_incident",
        "retry_webhook",
        "requeue_agent_run",
        "circuit_break_ingestion",
    },
}


def test_actions_for_roles_pure():
    for role, expected_ids in _EXPECTED.items():
        got = {a["action_id"] for a in actions_for_roles(frozenset({role}))}
        assert got == expected_ids, role


def test_every_action_declares_a_scope_and_endpoint():
    for role, actions in (
        (r, actions_for_roles(frozenset({r}))) for r in _EXPECTED
    ):
        for a in actions:
            assert a["scope"], (role, a["action_id"])
            assert a["endpoint"].startswith(("POST ", "GET ")), a["action_id"]
            assert isinstance(a["requires_rationale_chars"], int)


pytestmark = pytestmark_db


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        ("sbs:conduct:analyst", _EXPECTED[ROLE_ANALYST]),
        ("sbs:conduct:supervisor", _EXPECTED[ROLE_SUPERVISOR]),
        ("sbs:conduct:head", _EXPECTED[ROLE_UNIT_HEAD]),
        ("sbs:superintendent", _EXPECTED[ROLE_SUPERINTENDENT]),
        ("sbs:sbs_it", _EXPECTED[ROLE_SBS_IT]),
    ],
)
async def test_actions_endpoint_per_persona(secret_app, role, expected):
    transport = ASGITransport(app=secret_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/v1/internal/cockpit/actions", headers=hdr(role))
    assert r.status_code == 200
    got = {a["action_id"] for a in r.json()["actions"]}
    assert got == expected
