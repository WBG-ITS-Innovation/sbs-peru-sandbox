# SPDX-License-Identifier: Apache-2.0
"""Ingest-time agent entry point: DIValeVale first, then the Part-12 chain.

``ingestion/pipeline.py`` states the contract — "DIValeVale validation is
the FIRST stage — every Tier-1 record passes through it before Triage" —
but its only callers were tests, so no runtime path ever ran DIValeVale
and ``validation_audit`` stayed empty. This module puts the documented
ordering on the real ingestion path.

Record-only on this surface, deliberately
=========================================

DIValeVale runs and writes its ``validation_audit`` row, but its verdict
does **not** currently suppress Triage here, and enrichment webhooks are
suppressed (``record_only=True``). Two facts force that, both verifiable:

1. **The identifier contract is unreconciled.** Pass 1 requires
   ``institution_code`` matching ``^[A-Z]{3}_[A-Z]+_\\d{3}$``. Every
   ingestion surface in this system identifies institutions as
   ``SBS-001234``; the dev-seed aliases are ``BANCO_DEMO_001`` /
   ``COOPAC_DEMO_002``. None of the three matches, and no
   institution_id -> institution_code mapping exists in the code or the
   database. The only string that satisfies the rule is the
   ``BCO_DEMO_001`` literal used inside DIValeVale's own tests.
2. **The canonical Tier-1 schema cannot carry the fields Pass 1 wants.**
   ADR 0026 fixes Tier 1 at a 15-field Anexo 1-A subset with no
   ``amount_claimed`` and no ``currency``. For the ``COBRO_INDEBIDO``
   family — where Pass 1 requires an amount — every legitimate record
   therefore lands on INSUFFICIENT, whose routing action is
   FLAGGED_FOR_ENRICHMENT, which delivers an outbound webhook asking the
   institution to resubmit. Enabling that as a gate would send a
   spurious enrichment request to an institution for essentially every
   complaint it files.

So the verdict is recorded and logged, not enforced. Flipping it to a
gate is a deliberate follow-up that needs (1) an authoritative
institution-code mapping and (2) an ADR 0026 decision on whether amount
and currency join the Tier-1 schema — neither of which is a
handover-window change. See docs/audit/2026-08-10-p0-fix-report.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.observability.logging import get_logger

_logger = get_logger(__name__)


@dataclass
class IngestAgentOutcome:
    """What the ingest-time agent stages decided, for logging/assertions."""

    complaint_id: str
    validation_verdict: str | None
    validation_routing_action: str | None
    validation_audit_id: str | None
    route_to: str | None


def canonical_record_to_validation_record(record: ComplaintRecord) -> dict:
    """Map a persisted canonical complaint onto DIValeVale's input shape.

    Only fields the canonical row genuinely carries are supplied — nothing
    is invented. ``amount_claimed`` and ``currency`` are absent because the
    Tier-1 subset has no such columns (ADR 0026), and ``institution_code``
    carries the SBS institution id, which is the identifier this system
    actually issues. Both gaps show up honestly in the audit row's
    ``failed_rules`` rather than being papered over.
    """
    return {
        "complaint_id": record.complaint_id,
        "institution_code": record.institution_id,
        "captured_at": record.received_at,
        "incident_date": record.received_date,
        "motivo_code": record.motivo_code,
        "narrative_es": record.description_text,
    }


async def run_agents_for_complaint(
    session: AsyncSession, *, complaint_id: str
) -> IngestAgentOutcome:
    """Run DIValeVale, then the triage -> investigation -> synthesis chain.

    The caller commits. Raises only on genuinely unexpected errors; the
    dispatch layer above is what guarantees the ingesting request is
    unaffected.
    """
    from sbs_api.agents.divalevale.agent import validate_tier1_record
    from sbs_api.agents.orchestrator import run_agent_pipeline

    record = (
        await session.execute(
            select(ComplaintRecord).where(
                ComplaintRecord.complaint_id == complaint_id
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise ValueError(f"complaint {complaint_id!r} not found")

    # Stage 1 — DIValeVale, ahead of Triage, per ingestion/pipeline.py.
    validation = await validate_tier1_record(
        session,
        record=canonical_record_to_validation_record(record),
        sbs_institution_id=record.institution_id,
        record_only=True,
    )
    _logger.info(
        "agents.validation.recorded",
        complaint_id=complaint_id,
        verdict=validation.verdict,
        routing_action=validation.routing_action,
        failed_rules=",".join(validation.failed_rules),
        enforced=False,
    )

    # Stage 2 — Triage and, where triage routes there, investigation +
    # synthesis. Not conditioned on the verdict; see the module docstring.
    outcome = await run_agent_pipeline(session, complaint_id=complaint_id)

    return IngestAgentOutcome(
        complaint_id=complaint_id,
        validation_verdict=validation.verdict,
        validation_routing_action=validation.routing_action,
        validation_audit_id=validation.audit_id,
        route_to=outcome.route_to,
    )
