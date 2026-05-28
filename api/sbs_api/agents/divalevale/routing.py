"""DIValeVale tier-differentiated routing decisions (P-RESHAPE-8).

Pure decision helpers — no DB, no I/O. The agent orchestrator
(``agent.py``) applies these then persists audit + fires webhooks.
"""

from __future__ import annotations

from dataclasses import dataclass

from sbs_api.agents.divalevale.pass1_schema import Verdict

# Tier-2 quarantine thresholds (locked).
BATCH_INSUFFICIENT_FRACTION = 0.20  # >= 20% INSUFFICIENT → quarantine
# (>= 1 INVALID row also quarantines.)


@dataclass(frozen=True)
class BatchDecision:
    quarantine: bool
    reason: str  # "invalid_present" | "insufficient_fraction" | "accepted"
    valid: int
    recoverable: int
    insufficient: int
    invalid: int


def decide_batch(verdicts: list[Verdict]) -> BatchDecision:
    total = len(verdicts) or 1
    valid = sum(1 for v in verdicts if v == Verdict.VALID)
    recoverable = sum(1 for v in verdicts if v == Verdict.RECOVERABLE)
    insufficient = sum(1 for v in verdicts if v == Verdict.INSUFFICIENT)
    invalid = sum(1 for v in verdicts if v == Verdict.INVALID)

    if invalid >= 1:
        reason = "invalid_present"
        quarantine = True
    elif insufficient / total >= BATCH_INSUFFICIENT_FRACTION:
        reason = "insufficient_fraction"
        quarantine = True
    else:
        reason = "accepted"
        quarantine = False
    return BatchDecision(
        quarantine=quarantine,
        reason=reason,
        valid=valid,
        recoverable=recoverable,
        insufficient=insufficient,
        invalid=invalid,
    )


def tier1_routing_action(verdict: Verdict) -> str:
    """Map a Tier-1 record verdict (post Pass-2 recovery) to a routing
    action. RECOVERABLE is resolved by the caller to VALID-after-recovery
    before this is consulted for the final action."""
    if verdict == Verdict.VALID:
        return "PROCEEDED_TO_TRIAGE"
    if verdict == Verdict.INSUFFICIENT:
        return "FLAGGED_FOR_ENRICHMENT"
    if verdict == Verdict.INVALID:
        return "REJECTED"
    # RECOVERABLE that could not be fully recovered → enrichment.
    return "FLAGGED_FOR_ENRICHMENT"
