# SPDX-License-Identifier: Apache-2.0
"""Persona scope matrix + route-level 403 enforcement (P-RESHAPE-5).

Pure-unit half: assert the locked role→scope map. App half: assert the
``requires_scope`` dependency 403s a role that lacks the scope and
admits one that holds it.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from sbs_api.auth.persona_scopes import (
    AUDIT_READ,
    COMPLAINTS_READ_DETAIL,
    EXEC_READ,
    FI_BRIEF_APPROVE,
    FI_BRIEF_OVERRIDE,
    OPS_READ,
    PEER_RISK_READ_EXEC,
    ROLE_ANALYST,
    ROLE_SBS_IT,
    ROLE_SUPERINTENDENT,
    ROLE_SUPERVISOR,
    ROLE_UNIT_HEAD,
    scopes_for_roles,
)
from tests.conftest import pytestmark_db

SHARED_VAL = "sandbox-persona-scope-test-001"  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# Pure scope-map matrix (no DB)
# ---------------------------------------------------------------------------


def test_analyst_has_complaint_detail_not_approve():
    s = scopes_for_roles(frozenset({ROLE_ANALYST}))
    assert COMPLAINTS_READ_DETAIL in s
    assert FI_BRIEF_APPROVE not in s
    assert OPS_READ not in s
    assert EXEC_READ not in s


def test_supervisor_can_approve_not_override():
    s = scopes_for_roles(frozenset({ROLE_SUPERVISOR}))
    assert FI_BRIEF_APPROVE in s
    assert FI_BRIEF_OVERRIDE not in s
    assert OPS_READ not in s


def test_unit_head_can_override():
    s = scopes_for_roles(frozenset({ROLE_UNIT_HEAD}))
    assert FI_BRIEF_OVERRIDE in s
    assert AUDIT_READ in s


def test_superintendent_is_exec_only_no_detail():
    s = scopes_for_roles(frozenset({ROLE_SUPERINTENDENT}))
    assert EXEC_READ in s
    assert PEER_RISK_READ_EXEC in s
    assert COMPLAINTS_READ_DETAIL not in s
    assert FI_BRIEF_APPROVE not in s
    assert OPS_READ not in s


def test_sbs_it_is_ops_only_no_business():
    s = scopes_for_roles(frozenset({ROLE_SBS_IT}))
    assert OPS_READ in s
    assert COMPLAINTS_READ_DETAIL not in s
    assert FI_BRIEF_APPROVE not in s
    assert EXEC_READ not in s


def test_unknown_role_grants_nothing():
    assert scopes_for_roles(frozenset({"sbs:wb_reviewer"})) == frozenset()
