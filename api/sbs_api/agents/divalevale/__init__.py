# SPDX-License-Identifier: Apache-2.0
"""DIValeVale — pre-ingestion data-quality validation agent (P-RESHAPE-8).

One of the three FI-facing agents with a character name (DIValeVale /
Reclamito / Lupaman). Sits BEFORE Triage in the ingestion pipeline:
every record passes through DIValeVale first. Two passes —
deterministic schema/completeness (Pass 1) and, only for recoverable
gaps, narrative-field extraction (Pass 2, regex + sparing on-prem LLM).
"""

AGENT_ID = "divalevale"
DISPLAY_NAME_ES = "DIValeVale"
DISPLAY_NAME_EN = "DIValeVale"

from sbs_api.agents.divalevale.pass1_schema import (  # noqa: E402
    Verdict,
    run_pass1,
)

__all__ = ["AGENT_ID", "DISPLAY_NAME_ES", "DISPLAY_NAME_EN", "Verdict", "run_pass1"]
