# SPDX-License-Identifier: Apache-2.0
"""DIValeVale orchestration (P-RESHAPE-8).

Runs Pass 1 → (RECOVERABLE only) Pass 2 → tier-differentiated routing,
persisting a ``validation_audit`` row and firing the FI webhook where
the routing action requires it. On-prem only (cloud rejected).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.agents.divalevale.audit import write_audit
from sbs_api.agents.divalevale.pass1_schema import Pass1Result, Verdict, run_pass1
from sbs_api.agents.divalevale.pass2_extraction import Pass2Result, run_pass2
from sbs_api.agents.divalevale.routing import BatchDecision, decide_batch, tier1_routing_action
from sbs_api.agents.providers import get_provider
from sbs_api.agents.providers.base import ModelProvider
from sbs_api.db.models.validation_audit import EnrichmentRequest, ValidationBatch
from sbs_api.webhooks.validation_delivery import (
    build_batch_rejection_payload,
    build_enrichment_request_payload,
    deliver_batch_rejection,
    deliver_enrichment_request,
)

_ALLOWED_PROVIDERS = {"on_prem", "replay", "mock"}
ENRICHMENT_BUSINESS_DAYS = 5
RESUBMIT_URL = "https://api-sandbox.sbs.gob.pe/v1/sandbox/complaints/granular"


@dataclass
class ValidationResult:
    complaint_id: str | None
    verdict: str
    routing_action: str
    failed_rules: list[str]
    pass2_invoked: bool
    recovered_record: dict[str, Any]
    audit_id: str
    proceeds_to_triage: bool
    flagged_for_review: bool = False
    enrichment_request_id: str | None = None


def _ensure_on_prem(provider: ModelProvider) -> None:
    if provider.name not in _ALLOWED_PROVIDERS:
        raise RuntimeError(
            f"DIValeVale requires an on-prem provider in v1; got "
            f"'{provider.name}'. Cloud Pass-2 extraction is gated."
        )


def _business_days_from(start: datetime, days: int) -> datetime:
    d = start
    added = 0
    while added < days:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


async def _apply_recoveries(record: dict[str, Any], pass2: Pass2Result) -> dict[str, Any]:
    recovered = dict(record)
    for r in pass2.recoveries:
        if r.field_recovered:
            recovered[r.field_name] = r.value
            recovered.setdefault("_recovered_fields", {})[r.field_name] = {
                "source": r.recovery_source,
                "confidence": r.recovery_confidence,
            }
    return recovered


async def validate_tier1_record(
    session: AsyncSession,
    *,
    record: dict[str, Any],
    sbs_institution_id: str,
    provider: ModelProvider | None = None,
    now: datetime | None = None,
    sender: Any = None,
    record_only: bool = False,
) -> ValidationResult:
    """Tier-1 individual path. Returns a ValidationResult; the caller
    proceeds to Triage only when ``proceeds_to_triage`` is True.

    ``record_only=True`` writes the ``validation_audit`` row but skips the
    FLAGGED_FOR_ENRICHMENT side effects — the EnrichmentRequest row and the
    outbound webhook asking the institution to resubmit. The canonical
    Tier-1 ingest path uses it because that surface cannot yet satisfy the
    Pass-1 rules (see sbs_api.agents.ingest_entry), so firing enrichment
    requests from there would mean one spurious webhook per complaint.
    Defaults to False, leaving every existing caller unchanged."""
    provider = provider or get_provider()
    _ensure_on_prem(provider)
    now = now or datetime.now(tz=timezone.utc)
    started = datetime.now(tz=timezone.utc)

    complaint_id = record.get("complaint_id")
    institution_code = str(record.get("institution_code") or "")

    p1 = run_pass1(record, now=now)
    pass2: Pass2Result | None = None
    recovered = dict(record)
    final_verdict = p1.verdict

    if p1.verdict == Verdict.RECOVERABLE:
        pass2 = await run_pass2(record, p1.recoverable_fields, provider=provider)
        recovered = await _apply_recoveries(record, pass2)
        # Re-run Pass 1 on the recovered record to settle the verdict.
        p1b = run_pass1(recovered, now=now)
        final_verdict = p1b.verdict if p1b.verdict != Verdict.RECOVERABLE else (
            Verdict.INSUFFICIENT if pass2.flagged_for_review else Verdict.RECOVERABLE
        )

    routing_action = tier1_routing_action(final_verdict)
    proceeds = routing_action == "PROCEEDED_TO_TRIAGE"
    latency = int((datetime.now(tz=timezone.utc) - started).total_seconds() * 1000)

    audit = await write_audit(
        session,
        complaint_id=complaint_id,
        institution_code=institution_code,
        verdict=final_verdict.value,
        failed_rules=p1.failed_rules,
        routing_action=routing_action,
        tier="TIER_1",
        pass2_invoked=bool(pass2 and pass2.llm_invoked),
        pass2_recoveries=pass2.as_audit() if pass2 else None,
        pass2_model_id=pass2.llm_model_id if pass2 else None,
        latency_ms=latency,
        now=now,
    )

    enrichment_id: str | None = None
    if routing_action == "FLAGGED_FOR_ENRICHMENT" and not record_only:
        enrichment_id = await _flag_for_enrichment(
            session,
            complaint_id=complaint_id,
            institution_code=institution_code,
            sbs_institution_id=sbs_institution_id,
            missing_fields=p1.failed_rules,
            now=now,
            sender=sender,
        )

    return ValidationResult(
        complaint_id=complaint_id,
        verdict=final_verdict.value,
        routing_action=routing_action,
        failed_rules=p1.failed_rules,
        pass2_invoked=bool(pass2 and pass2.llm_invoked),
        recovered_record=recovered,
        audit_id=audit.audit_id,
        proceeds_to_triage=proceeds,
        flagged_for_review=bool(pass2 and pass2.flagged_for_review),
        enrichment_request_id=enrichment_id,
    )


async def _flag_for_enrichment(
    session: AsyncSession,
    *,
    complaint_id: str | None,
    institution_code: str,
    sbs_institution_id: str,
    missing_fields: list[str],
    now: datetime,
    sender: Any,
) -> str:
    request_id = str(uuid.uuid4())
    deadline = _business_days_from(now, ENRICHMENT_BUSINESS_DAYS)
    req = EnrichmentRequest(
        request_id=request_id,
        complaint_id=complaint_id or "UNKNOWN",
        institution_code=institution_code,
        requested_at=now,
        deadline=deadline,
        missing_fields=missing_fields,
        state="PENDING",
        delivery_status="PENDING",
        delivery_attempts=0,
    )
    session.add(req)
    await session.flush()

    payload = build_enrichment_request_payload(
        complaint_id=complaint_id or "UNKNOWN",
        missing_fields=missing_fields,
        deadline=deadline,
        resubmit_url=RESUBMIT_URL,
    )
    outcome = await deliver_enrichment_request(
        session, sbs_institution_id=sbs_institution_id, payload=payload, sender=sender
    )
    req.delivery_status = outcome.status
    req.delivery_attempts = outcome.attempts
    await session.flush()
    return request_id


async def fulfill_enrichment(
    session: AsyncSession,
    *,
    complaint_id: str,
    enriched_record: dict[str, Any],
    sbs_institution_id: str,
    provider: ModelProvider | None = None,
    now: datetime | None = None,
) -> ValidationResult:
    """FI resubmitted an enriched record. Re-run DIValeVale; on VALID,
    mark the enrichment FULFILLED. If still not VALID after this one
    cycle, escalate (no auto second request)."""
    now = now or datetime.now(tz=timezone.utc)
    result = await validate_tier1_record(
        session,
        record=enriched_record,
        sbs_institution_id=sbs_institution_id,
        provider=provider,
        now=now,
    )
    pending = (
        await session.execute(
            select(EnrichmentRequest)
            .where(EnrichmentRequest.complaint_id == complaint_id)
            .where(EnrichmentRequest.state == "PENDING")
        )
    ).scalars().all()
    for req in pending:
        if result.proceeds_to_triage:
            req.state = "FULFILLED"
            req.fulfilled_at = now
            req.fulfilled_via_complaint_version = enriched_record.get("version") or "v2"
        else:
            req.state = "ESCALATED"
    await session.flush()
    return result


@dataclass
class BatchValidationResult:
    batch_id: str
    decision: BatchDecision
    state: str  # QUARANTINED | ACCEPTED | REPLACED
    triage_eligible_records: list[dict[str, Any]] = field(default_factory=list)
    diagnostic_report: dict[str, Any] | None = None


async def validate_tier2_batch(
    session: AsyncSession,
    *,
    batch_id: str,
    records: list[dict[str, Any]],
    sbs_institution_id: str,
    institution_code: str,
    provider: ModelProvider | None = None,
    now: datetime | None = None,
    sender: Any = None,
) -> BatchValidationResult:
    """Tier-2 batch path. Evaluates every row, aggregates, quarantines on
    >=1 INVALID or >=20% INSUFFICIENT, and delivers the diagnostic report.
    Idempotent on batch_id: a resubmit with the same id REPLACES a prior
    quarantined batch."""
    provider = provider or get_provider()
    _ensure_on_prem(provider)
    now = now or datetime.now(tz=timezone.utc)

    # Idempotency: a resubmit with the same batch_id REPLACES the prior
    # evaluation. Since batch_id is the PK we update the row in place
    # (a prior quarantine is overwritten by the new verdict).
    prior = (
        await session.execute(
            select(ValidationBatch).where(ValidationBatch.batch_id == batch_id)
        )
    ).scalar_one_or_none()
    is_resubmit = prior is not None

    # ``pass1_verdicts`` drives the quarantine decision (the 6/2/1/1
    # distribution is a Pass-1 fact). Triage eligibility is decided on the
    # POST-Pass-2 verdict (a RECOVERABLE row that recovers becomes eligible).
    pass1_verdicts: list[Verdict] = []
    per_row_codes: list[dict[str, Any]] = []
    triage_eligible: list[dict[str, Any]] = []

    for record in records:
        p1 = run_pass1(record, now=now)
        pass1_verdicts.append(p1.verdict)
        recovered = dict(record)
        pass2: Pass2Result | None = None
        final_verdict = p1.verdict
        if p1.verdict == Verdict.RECOVERABLE:
            pass2 = await run_pass2(record, p1.recoverable_fields, provider=provider)
            recovered = await _apply_recoveries(record, pass2)
            p1b = run_pass1(recovered, now=now)
            final_verdict = p1b.verdict
        per_row_codes.append(
            {
                "row_ref": record.get("complaint_id") or record.get("row_ref"),
                "verdict": p1.verdict.value,
                "codes": p1.failed_rules,  # codes only — no narrative
            }
        )
        if final_verdict == Verdict.VALID:
            triage_eligible.append(recovered)
        # Per-row audit records the Pass-1 verdict + the recovery detail.
        await write_audit(
            session,
            complaint_id=record.get("complaint_id"),
            institution_code=institution_code,
            verdict=p1.verdict.value,
            failed_rules=p1.failed_rules,
            routing_action="QUARANTINED_BATCH",
            tier="TIER_2",
            pass2_invoked=bool(pass2 and pass2.llm_invoked),
            pass2_recoveries=pass2.as_audit() if pass2 else None,
            pass2_model_id=pass2.llm_model_id if pass2 else None,
            batch_id=batch_id,
            now=now,
        )

    decision = decide_batch(pass1_verdicts)
    state = "QUARANTINED" if decision.quarantine else "ACCEPTED"
    diagnostic: dict[str, Any] | None = None
    if decision.quarantine:
        diagnostic = {
            "batch_id": batch_id,
            "reason": decision.reason,
            "row_count": len(records),
            "per_row_failure_codes": per_row_codes,
        }

    if is_resubmit:
        # Update the existing row in place — the prior content is replaced.
        batch = prior
        batch.institution_code = institution_code
        batch.received_at = now
        batch.row_count = len(records)
        batch.valid_count = decision.valid
        batch.recoverable_count = decision.recoverable
        batch.insufficient_count = decision.insufficient
        batch.invalid_count = decision.invalid
        batch.state = state
        batch.diagnostic_report = diagnostic
        batch.replaced_at = now
        batch.replaced_by_batch_id = batch_id
    else:
        batch = ValidationBatch(
            batch_id=batch_id,
            institution_code=institution_code,
            received_at=now,
            row_count=len(records),
            valid_count=decision.valid,
            recoverable_count=decision.recoverable,
            insufficient_count=decision.insufficient,
            invalid_count=decision.invalid,
            state=state,
            diagnostic_report=diagnostic,
        )
        session.add(batch)
    await session.flush()

    if decision.quarantine:
        payload = build_batch_rejection_payload(
            batch_id=batch_id,
            row_count=len(records),
            per_row_codes=per_row_codes,
            resubmit_url=RESUBMIT_URL,
        )
        await deliver_batch_rejection(
            session, sbs_institution_id=sbs_institution_id, payload=payload, sender=sender
        )
        triage_eligible = []  # no rows reach Triage from a quarantined batch

    return BatchValidationResult(
        batch_id=batch_id,
        decision=decision,
        state=batch.state,
        triage_eligible_records=triage_eligible,
        diagnostic_report=diagnostic,
    )
