# SPDX-License-Identifier: Apache-2.0
"""Persona home-route resolution (P-RESHAPE-5).

Pure-unit: the token's roles resolve to exactly one home persona route.
A multi-role demo account lands on the most-privileged home. Unknown /
retired roles resolve to no home.
"""

from __future__ import annotations

from sbs_api.auth.persona_scopes import (
    PERSONA_HOME_ROUTE,
    ROLE_ANALYST,
    ROLE_SBS_IT,
    ROLE_SUPERINTENDENT,
    ROLE_SUPERVISOR,
    ROLE_UNIT_HEAD,
    primary_persona,
)


def test_each_role_maps_to_its_home():
    assert PERSONA_HOME_ROUTE[ROLE_ANALYST] == "analyst"
    assert PERSONA_HOME_ROUTE[ROLE_SUPERVISOR] == "supervisor"
    assert PERSONA_HOME_ROUTE[ROLE_UNIT_HEAD] == "unit-head"
    assert PERSONA_HOME_ROUTE[ROLE_SUPERINTENDENT] == "superintendent"
    assert PERSONA_HOME_ROUTE[ROLE_SBS_IT] == "it"


def test_single_role_resolves_home():
    assert primary_persona(frozenset({ROLE_ANALYST})) == ROLE_ANALYST
    assert primary_persona(frozenset({ROLE_SBS_IT})) == ROLE_SBS_IT


def test_multi_role_resolves_most_privileged():
    # A demo account holding both analyst + unit_head lands on unit-head.
    assert (
        primary_persona(frozenset({ROLE_ANALYST, ROLE_UNIT_HEAD}))
        == ROLE_UNIT_HEAD
    )
    # supervisor beats analyst.
    assert (
        primary_persona(frozenset({ROLE_ANALYST, ROLE_SUPERVISOR}))
        == ROLE_SUPERVISOR
    )


def test_unknown_role_has_no_home():
    assert primary_persona(frozenset({"sbs:wb_reviewer"})) is None
    assert primary_persona(frozenset()) is None


def test_wrong_persona_url_redirect_target_is_actual_home():
    """The BFF redirects a wrong-persona URL hit to the user's real home.
    The redirect target is derived purely from the token roles, never
    from the requested URL — so an analyst hitting /it/ is sent to
    /analyst/."""
    roles = frozenset({ROLE_ANALYST})
    requested = "it"  # analyst tries to open the IT view
    home = PERSONA_HOME_ROUTE[primary_persona(roles)]
    assert home != requested
    assert home == "analyst"
