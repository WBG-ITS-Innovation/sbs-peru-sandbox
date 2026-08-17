# SPDX-License-Identifier: Apache-2.0
"""Resolution-status state machine — unit tests.

No FastAPI, no DB. Exercises the rules ADR 0028 §9 locks. The terminal-state
reason-required rule remains a model-validator concern in
``ComplaintStatusPatch``; this module covers transitions only.
"""

from __future__ import annotations

import pytest

from sbs_api.models.anexo_1a import ResolutionStatus
from sbs_api.state_machine.resolution_status import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    is_allowed,
    is_terminal,
)


@pytest.mark.parametrize(
    "current,requested",
    [
        (ResolutionStatus.PENDIENTE, ResolutionStatus.PENDIENTE),
        (ResolutionStatus.PENDIENTE, ResolutionStatus.ATENDIDO),
        (ResolutionStatus.PENDIENTE, ResolutionStatus.ANULADO),
    ],
)
def test_allowed_transitions_from_pendiente(current, requested):
    assert is_allowed(current, requested)


@pytest.mark.parametrize(
    "current,requested",
    [
        (ResolutionStatus.ATENDIDO, ResolutionStatus.PENDIENTE),
        (ResolutionStatus.ATENDIDO, ResolutionStatus.ANULADO),
        (ResolutionStatus.ATENDIDO, ResolutionStatus.ATENDIDO),
        (ResolutionStatus.ANULADO, ResolutionStatus.PENDIENTE),
        (ResolutionStatus.ANULADO, ResolutionStatus.ATENDIDO),
        (ResolutionStatus.ANULADO, ResolutionStatus.ANULADO),
    ],
)
def test_forbidden_transitions_from_terminal(current, requested):
    assert not is_allowed(current, requested)


def test_terminal_states():
    assert is_terminal(ResolutionStatus.ATENDIDO)
    assert is_terminal(ResolutionStatus.ANULADO)
    assert not is_terminal(ResolutionStatus.PENDIENTE)


def test_terminal_states_have_no_outbound():
    for s in TERMINAL_STATES:
        assert ALLOWED_TRANSITIONS[s] == frozenset()
