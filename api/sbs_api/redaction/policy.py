# SPDX-License-Identifier: Apache-2.0
"""Policy constants for deterministic PII redaction (P11A / ADR 0044).

Two things live in this module:

* ``POLICY_VERSION`` — the string written to every redaction record
  and persisted on the matching ``raw_complaints`` row.
* The known-demo-name allowlist — a small set of names that appear in
  the synthetic demo data the sandbox ships. Real production redaction
  would supply a per-institution allowlist or call a Spanish-language
  NER model; for the sandbox demo a fixed list is enough to prove the
  pipeline shape without inventing a name detector.
"""

from __future__ import annotations

from dataclasses import dataclass

POLICY_VERSION = "pii-redaction-demo-v1"


@dataclass(frozen=True)
class RedactionEntity:
    """One detected PII span.

    ``matched_value`` is **never** persisted outside ``raw_complaints``
    — the engine returns it only so the caller can write it to that
    restricted table. Anything that leaves the demo endpoint (response
    body, agent_runs, SSE payload, audit row) carries only ``kind``,
    ``replacement``, ``span``, ``rule_id`` and ``confidence``.
    """

    kind: str
    rule_id: str
    span: tuple[int, int]
    replacement: str
    confidence: float
    matched_value: str


# Demo-scoped allowlist of person names that appear in the synthetic
# data. Real ingestion would either use an institution-supplied
# allowlist or a NER model; for the sandbox demo the fixed list is
# sufficient.
DEMO_KNOWN_NAMES: tuple[str, ...] = (
    "Carlos Rodríguez Mendoza",
    "Carlos Rodriguez Mendoza",
    "Juan Pérez",
    "Juan Perez",
    "Supervisor Velásquez",
    "Supervisor Velasquez",
)
