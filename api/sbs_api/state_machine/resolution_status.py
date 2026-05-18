"""Resolution-status state machine.

ADR 0028 §9 locks the permitted transitions. Decoupled from the route handler
so the rules can be unit-tested without spinning up the app and re-used by
the audit log and the approval-queue path that lands in Part 6.
"""

from __future__ import annotations

from sbs_api.models.anexo_1a import ResolutionStatus

# Allowed transitions as an explicit graph. Reading the table:
#   pendiente → atendido        (terminal)
#   pendiente → anulado         (terminal)
#   pendiente → pendiente       (status-edit, no state change — allowed)
# Any other transition is forbidden. `atendido` and `anulado` are terminal.
ALLOWED_TRANSITIONS: dict[ResolutionStatus, frozenset[ResolutionStatus]] = {
    ResolutionStatus.PENDIENTE: frozenset(
        {
            ResolutionStatus.PENDIENTE,
            ResolutionStatus.ATENDIDO,
            ResolutionStatus.ANULADO,
        }
    ),
    ResolutionStatus.ATENDIDO: frozenset(),
    ResolutionStatus.ANULADO: frozenset(),
}

TERMINAL_STATES: frozenset[ResolutionStatus] = frozenset(
    {ResolutionStatus.ATENDIDO, ResolutionStatus.ANULADO}
)


def is_terminal(state: ResolutionStatus) -> bool:
    return state in TERMINAL_STATES


def is_allowed(current: ResolutionStatus, requested: ResolutionStatus) -> bool:
    """Return True iff a transition from ``current`` to ``requested`` is permitted.

    Self-edits on ``pendiente → pendiente`` are allowed so a client can update
    notes without changing the lifecycle state. Self-edits on terminal states
    are forbidden because the terminal-state rule from Prompt 5's adversarial
    finding (reason required) implies a state change.
    """

    return requested in ALLOWED_TRANSITIONS.get(current, frozenset())
