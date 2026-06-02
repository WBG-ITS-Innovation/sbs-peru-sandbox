"""End-to-end orchestrator for the P11A demo ingestion pipeline.

Pipeline order:

1. Persist raw payload + raw narrative to ``raw_complaints`` (the
   only place raw PII lives).
2. Run deterministic redaction over the narrative and response_detail.
3. Persist a canonical ``complaints`` row with the redacted text and
   ``source='api_realtime'``. The id-pattern matches the existing
   institutional convention (``BCO-YYYY-NNNNNNN``).
4. Run deterministic data-quality checks on the redacted narrative
   plus the structured fields.
5. Write one ``agent_runs`` row covering both steps. The anonymizer
   tool_call carries the safe redaction record (no raw values); the
   DQ report sits in ``final_output.data_quality`` so the JSON Schema
   ``tool_name`` enum does not need widening. The findings builder
   continues to find the anonymizer tool_call via the same
   ``tool_name == 'anonymizer'`` selector.
6. Record six audit-chain rows, all carrying redacted values only.
7. Publish one ``complaint.received`` event on the ``cockpit`` SSE
   topic with the cockpit-card shape the existing reducer already
   handles.

Returns a :class:`DemoIngestionOutcome` carrying every id and the
timeline the UI renders.
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from sbs_api.audit import record_audit_event
from sbs_api.data_quality import POLICY_VERSION as DQ_POLICY_VERSION
from sbs_api.data_quality import run_checks as run_dq_checks
from sbs_api.data_quality.annex_1a_rules import (
    POLICY_VERSION as ANNEX_1A_POLICY_VERSION,
    run_annex_1a_checks,
)
from sbs_api.db.models.agent_run import AgentRun
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.institution import InstitutionRecord
from sbs_api.db.models.raw_complaint import RawComplaint
from sbs_api.models.demo_ingestion import DemoSubmissionRequest
from sbs_api.redaction import POLICY_VERSION as REDACTION_POLICY_VERSION
from sbs_api.redaction import redact
from sbs_api.redaction.engine import masked_preview
from sbs_api.sse import get_bus
from sbs_api.taxonomy import (
    DICTIONARY_VERSION as TAXONOMY_DICTIONARY_VERSION,
    NormalizationOutcome,
    normalize_payload,
)

# Map institution_id → canonical complaint-id prefix used by the
# seeded BANCO_DEMO_001 / COOPAC_DEMO_002 rows so the cockpit's
# tier-1 / tier-2 panels bucket new cards consistently.
_INSTITUTION_TO_PREFIX: dict[str, str] = {
    "SBS-001234": "BCO",
    "SBS-005678": "COP",
}

_AGENT_NAME = "live-ingestion-orchestrator"
_AGENT_VERSION = f"{_AGENT_NAME}-0.1.0"
_ANONYMIZER_TOOL_VERSION = "anonymizer-0.1.0"

_PRODUCT_DEFAULT = "TARJETA_CREDITO"
_CHANNEL_DEFAULT = "APP_MOVIL"
_MOTIVO_DEFAULT = "COBRO_INDEBIDO"
_SUBMISSION_METHOD_DEFAULT = "APP_MOVIL"
_LANGUAGE_DEFAULT = "es"
_DISTRICT_DEFAULT = "150100"
_AGE_RANGE_DEFAULT = "35_44"
_DOC_TYPE_DEFAULT = "DNI"
_RESOLUTION_DEFAULT = "pendiente"
_SEVERITY_DEFAULT = "MEDIUM"


@dataclass
class DemoIngestionOutcome:
    complaint_id: str
    raw_complaint_id: str
    institution_id: str
    institution_name: str | None
    agent_run_id: str
    event_id: int | None
    timeline: list[dict[str, str]]
    redaction_diff: dict[str, Any]
    data_quality: dict[str, Any]
    # P11 DQ completion — Annex 1-A 21-rule report. Distinct from the
    # legacy ``data_quality`` envelope (which carries the original six
    # rules unchanged) so existing consumers see no shape drift.
    annex_1a_data_quality: dict[str, Any] | None = None
    # P11 demo-ready overlay — every (field, original → canonical)
    # pair the taxonomy dictionary mapped on this submission. The
    # supervisor UI surfaces this list under the Findings panel; the
    # ``flag_unknown_taxonomy`` flag lights up when ≥ 1 field carried
    # a surface form the dictionary did not recognise.
    taxonomy_normalizations: list[dict[str, str]] = field(default_factory=list)
    flag_unknown_taxonomy: bool = False


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _ts(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _generate_complaint_id(institution_id: str) -> str:
    """Build a unique complaint_id matching ``^[A-Z0-9]{1,4}-\\d{4}-\\d{6,10}$``.

    The institution prefix follows the seed convention so the cockpit
    Tier panels bucket new cards consistently. The numeric tail is
    drawn from ``secrets`` so concurrent demo runs do not collide
    (the demo endpoint also retries on PK collision).
    """

    prefix = _INSTITUTION_TO_PREFIX.get(institution_id, "DEMO")
    year = datetime.now(tz=timezone.utc).year
    # 7-digit tail keeps the id within the existing seed numeric range.
    tail = secrets.randbelow(9_000_000) + 1_000_000  # 1_000_000 .. 9_999_999
    return f"{prefix}-{year}-{tail:07d}"


def _parse_received_date(value: str | None) -> date:
    if not value:
        return _now().date()
    try:
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        return date.fromisoformat(value)
    except ValueError:
        return _now().date()


def _safe_or_default(value: str | None, default: str) -> str:
    cleaned = (value or "").strip()
    return cleaned if cleaned else default


def _description_preview(text: str, *, limit: int = 120) -> str:
    if not text:
        return ""
    return text[:limit] + ("…" if len(text) > limit else "")


def _entity_count_by_kind(entities: tuple) -> dict[str, int]:
    out: dict[str, int] = {}
    for ent in entities:
        out[ent.kind] = out.get(ent.kind, 0) + 1
    return out


async def _resolve_institution_name(
    session: AsyncSession, institution_id: str
) -> str | None:
    inst = await session.get(InstitutionRecord, institution_id)
    return inst.display_name if inst else None


async def _load_known_institution_ids(session: AsyncSession) -> frozenset[str]:
    """Snapshot the set of onboarded institution_ids for DQ-A1A-027.

    Cheap one-shot SELECT. The orchestrator runs at most once per
    submission so we don't bother caching across requests.
    """

    rows = (
        await session.execute(
            select(InstitutionRecord.institution_id).where(
                InstitutionRecord.onboarded.is_(True)
            )
        )
    ).all()
    return frozenset(r[0] for r in rows)


async def _insert_complaint_with_retry(
    session: AsyncSession,
    *,
    institution_id: str,
    redacted_narrative: str,
    redacted_descripcion_resolucion: str | None,
    request: DemoSubmissionRequest,
    severity: str,
    received_date: date,
    taxonomy_canonical: dict[str, str],
) -> ComplaintRecord:
    """Insert a ComplaintRecord, retrying on PK collision up to 5 times.

    ``taxonomy_canonical`` is the per-field canonical map produced by
    the taxonomy normalization step. When a field appears in that map
    its canonical code wins over the raw value (so
    ``"Crédito de consumo"`` lands in the column as
    ``"credito_consumo"``); when it doesn't, the raw value is written
    through with ``flag_unknown_taxonomy`` already set elsewhere.
    """

    def _normalized(
        field_path: str, raw: str | None, default: str, *, max_len: int = 32
    ) -> str:
        """Pick the value for a canonical column.

        Order: dictionary-mapped canonical → raw (if it fits) → default.
        The real Annex 1-A sample carries surface forms longer than the
        canonical varchar(32) columns (e.g. ``"Cobros indebidos de
        intereses, comisiones, gastos y tributos..."``). When the
        taxonomy dictionary doesn't recognise the value, we fall back
        to the default code rather than blowing up the insert; the
        raw value is still preserved in the agent_run
        ``taxonomy_normalizations`` payload, the
        ``taxonomy-unknown-term`` audit row, and the raw_complaints
        store. ``flag_unknown_taxonomy=True`` lets the UI highlight
        the row.
        """

        canonical = taxonomy_canonical.get(field_path)
        if canonical:
            return canonical
        cleaned = (raw or "").strip()
        if cleaned and len(cleaned) <= max_len:
            return cleaned
        return default

    fecha_resolucion = _parse_optional_date(request.fecha_resolucion)
    monto_pendiente = _parse_optional_decimal(request.monto_pendiente)
    def _fit_or_none(value: str | None, max_len: int) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if len(cleaned) <= max_len:
            return cleaned
        # Free-text values longer than the column simply don't fit
        # the canonical projection. The full text is preserved in
        # raw_complaints + the taxonomy audit row.
        return None

    tipo_resolucion = (
        taxonomy_canonical.get("tipo_resolucion")
        or _fit_or_none(request.tipo_resolucion, 64)
    )
    estado_reclamo = (
        taxonomy_canonical.get("status")
        or _fit_or_none(
            (request.status or "").strip().lower().replace(" ", "_") or None,
            32,
        )
    )

    last_exc: Exception | None = None
    for _ in range(5):
        complaint_id = _generate_complaint_id(institution_id)
        try:
            record = ComplaintRecord(
                complaint_id=complaint_id,
                institution_id=institution_id,
                received_date=received_date,
                complainant_doc_type=_DOC_TYPE_DEFAULT,
                product_category=_normalized(
                    "product", request.product, _PRODUCT_DEFAULT
                ),
                channel=_normalized(
                    "channel_in", request.channel_in, _CHANNEL_DEFAULT
                ),
                motivo_code=_normalized(
                    "motive", request.motive, _MOTIVO_DEFAULT
                ),
                severity=severity,
                description_text=redacted_narrative,
                description_language=_LANGUAGE_DEFAULT,
                complainant_age_range=_AGE_RANGE_DEFAULT,
                complainant_district=_DISTRICT_DEFAULT,
                submission_method=_normalized(
                    "channel_operation",
                    request.channel_operation,
                    _SUBMISSION_METHOD_DEFAULT,
                ),
                original_reference_id=None,
                resolution_status=_safe_or_default(
                    request.status, _RESOLUTION_DEFAULT
                ),
                source="api_realtime",
                client_submission_id=request.client_submission_id,
                fecha_resolucion=fecha_resolucion,
                tipo_resolucion=tipo_resolucion,
                descripcion_resolucion=redacted_descripcion_resolucion,
                estado_reclamo=estado_reclamo,
                monto_pendiente=monto_pendiente,
            )
            session.add(record)
            await session.flush()
            return record
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            await session.rollback()
    raise RuntimeError(
        f"could not insert demo complaint after retries: {last_exc!r}"
    ) from last_exc


def _parse_optional_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_optional_decimal(value: str | None) -> Any:
    """Parse a string into ``Decimal`` for the ``monto_pendiente`` column.

    Returns ``None`` for empty / unparseable input — the column is
    nullable, so swallowing a bad value is preferable to failing the
    submission outright. DQ checks already surface malformed amounts.
    """

    if not value:
        return None
    from decimal import Decimal, InvalidOperation

    try:
        return Decimal(value.strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None


def _build_anonymizer_tool_call(
    *,
    raw_complaint_id: str,
    redacted_text: str,
    safe_redactions: list[dict],
    started_at: datetime,
    ended_at: datetime,
) -> dict[str, Any]:
    """Build a tool_call dict that validates against the agent_run schema.

    Per ``docs/schemas/agent_run.schema.json`` the anonymizer call's
    ``output.redactions`` items are ``{kind, span}`` only — and the
    ``input.text`` is a non-empty string. We pass a reference token
    (not raw text) so the agent_runs row remains PII-free.
    """

    schema_redactions = [
        {"kind": r["kind"], "span": list(r["span"])} for r in safe_redactions
    ]
    return {
        "tool_name": "anonymizer",
        "tool_version": _ANONYMIZER_TOOL_VERSION,
        "started_at": _ts(started_at),
        "ended_at": _ts(ended_at),
        "input": {
            "text": f"raw-narrative-ref:{raw_complaint_id}",
            "policy_version": REDACTION_POLICY_VERSION,
        },
        "output": {
            "anonymized_text": redacted_text,
            "redactions": schema_redactions,
            "policy_version": REDACTION_POLICY_VERSION,
        },
        "status": "success",
        "error": None,
    }


async def run_demo_ingestion(
    session: AsyncSession,
    *,
    request: DemoSubmissionRequest,
    actor_id: str = "live-ingestion-orchestrator",
) -> DemoIngestionOutcome:
    """Execute the full demo ingestion pipeline against ``session``.

    The caller commits ``session``. The function performs one
    ``flush`` between each persistence step so a failure rolls back
    cleanly without partial state.
    """

    timeline: list[dict[str, str]] = []

    def step(name: str, detail: str | None = None) -> None:
        timeline.append({"event": name, "at": _ts(_now()), "detail": detail or ""})

    step("received", f"demo_scenario={request.demo_scenario or '-'}")

    # 1. raw_complaints — store the request verbatim. Only place raw
    #    PII lives. ``raw_descripcion_resolucion`` is the canonical-
    #    aligned column name for the DET_RES text added in the P11
    #    demo-ready overlay; ``raw_response_detail`` stays in place
    #    for the legacy migration window.
    raw_complaint_id = str(uuid.uuid4())
    raw_payload_dict = json.loads(request.model_dump_json())
    raw_row = RawComplaint(
        id=raw_complaint_id,
        canonical_complaint_id=None,
        institution_id=request.institution_id,
        client_submission_id=request.client_submission_id,
        raw_payload=raw_payload_dict,
        raw_narrative=request.narrative,
        raw_response_detail=request.response_detail,
        raw_descripcion_resolucion=request.response_detail,
        storage_policy="restricted-demo-pii-v1",
        redaction_policy_version=REDACTION_POLICY_VERSION,
    )
    session.add(raw_row)
    await session.flush()

    step("institution_authenticated_simulated", "shared-secret + role check")
    step("schema_validated", "Anexo 1-A-like fields parsed")

    # 1b. taxonomy normalization — runs before redaction so the audit
    #     row carries the original (non-PII) taxonomy values verbatim
    #     and the canonical persistence step downstream writes the
    #     normalized codes. Unknown surface forms do not block: the
    #     orchestrator records ``taxonomy-unknown-term`` warnings,
    #     writes the raw value through unchanged, and flips
    #     ``flag_unknown_taxonomy`` on the agent_run envelope.
    taxonomy_payload_in: dict[str, Any] = json.loads(request.model_dump_json())
    taxonomy_outcome: NormalizationOutcome = normalize_payload(taxonomy_payload_in)
    step(
        "taxonomy_normalized",
        f"mapped={len(taxonomy_outcome.normalizations)} "
        f"unknown={len(taxonomy_outcome.unknown_terms)} "
        f"dictionary={TAXONOMY_DICTIONARY_VERSION}",
    )

    # 2. redact narrative + response_detail.
    redaction_started_at = _now()
    narrative_result = redact(request.narrative)
    response_result = (
        redact(request.response_detail) if request.response_detail else None
    )
    redaction_ended_at = _now()

    institution_name = await _resolve_institution_name(
        session, request.institution_id
    )

    masked_before = masked_preview(request.narrative, narrative_result.entities)
    safe_entities = narrative_result.safe_entities()
    entity_counts = _entity_count_by_kind(narrative_result.entities)
    redaction_diff_payload = {
        "before_masked": masked_before,
        "after_redacted": narrative_result.redacted_text,
        "policy_version": REDACTION_POLICY_VERSION,
        "entities": safe_entities,
        "entity_count_by_kind": entity_counts,
    }
    step(
        "pii_redacted",
        f"entities={sum(entity_counts.values())} policy={REDACTION_POLICY_VERSION}",
    )

    # 3. canonical complaint persistence (with retry on PK collision).
    severity = (request.severity or _SEVERITY_DEFAULT).upper()
    received_date = _parse_received_date(request.received_at)
    redacted_resolution_text = (
        response_result.redacted_text if response_result else None
    )
    canonical = await _insert_complaint_with_retry(
        session,
        institution_id=request.institution_id,
        redacted_narrative=narrative_result.redacted_text,
        redacted_descripcion_resolucion=redacted_resolution_text,
        request=request,
        severity=severity,
        received_date=received_date,
        taxonomy_canonical=taxonomy_outcome.canonical,
    )

    # Re-add the raw row reference now that the canonical id exists.
    raw_row.canonical_complaint_id = canonical.complaint_id
    await session.flush()
    step(
        "canonical_complaint_persisted",
        f"complaint_id={canonical.complaint_id} source=api_realtime",
    )

    # 4. data-quality checks against the redacted narrative.
    dq_report = run_dq_checks(
        fields={
            "institution_complaint_id": request.institution_complaint_id,
            "product": request.product,
            "motive": request.motive,
            "channel_operation": request.channel_operation,
            "amount_claimed": request.amount_claimed,
        },
        redacted_narrative=narrative_result.redacted_text,
    )
    dq_payload = dq_report.as_dict()
    step(
        "data_quality_checks_completed",
        f"errors={len(dq_report.errors)} warnings={len(dq_report.warnings)} "
        f"policy={DQ_POLICY_VERSION}",
    )

    # 4b. Annex 1-A DQ rules (DQ-A1A-007..027) — additive on top of
    #     the legacy six rules. The dict-payload built below carries
    #     the FULL request shape so per-field rules can read each
    #     Annex 1-A acronym; rule code never touches the raw narrative
    #     (rule logic operates on structured fields only).
    known_iids = await _load_known_institution_ids(session)
    annex_1a_payload_in: dict[str, Any] = json.loads(request.model_dump_json())
    annex_1a_report = run_annex_1a_checks(
        annex_1a_payload_in, known_institutions=known_iids
    )
    annex_1a_payload = {
        **annex_1a_report.as_dict(),
        "policy_version": ANNEX_1A_POLICY_VERSION,
    }
    step(
        "annex_1a_checks_completed",
        f"errors={len(annex_1a_report.errors)} "
        f"warnings={len(annex_1a_report.warnings)} "
        f"policy={ANNEX_1A_POLICY_VERSION}",
    )

    # 5. agent_runs row. anonymizer tool_call only — the DQ report
    #    sits in final_output to keep the JSON Schema tool_name enum
    #    unchanged (ADR 0045 §Divergence).
    agent_run_id = str(uuid.uuid4())
    anonymizer_call = _build_anonymizer_tool_call(
        raw_complaint_id=raw_complaint_id,
        redacted_text=narrative_result.redacted_text,
        safe_redactions=safe_entities,
        started_at=redaction_started_at,
        ended_at=redaction_ended_at,
    )
    has_blocking_errors = (
        dq_report.has_blocking_errors or bool(annex_1a_report.errors)
    )
    run_status = "partial" if has_blocking_errors else "success"
    taxonomy_entries = taxonomy_outcome.to_agent_run_entries()
    final_output: dict[str, Any] = {
        "complaint_id": canonical.complaint_id,
        "raw_complaint_id": raw_complaint_id,
        "redaction": {
            "policy_version": REDACTION_POLICY_VERSION,
            "entity_count_by_kind": entity_counts,
        },
        "data_quality": dq_payload,
        "annex_1a_data_quality": annex_1a_payload,
        "summary": _description_preview(narrative_result.redacted_text),
        # P11 demo-ready overlay — top-level taxonomy_normalizations
        # entry per the prompt's agent_run JSON contract. List is
        # empty when every field was already canonical (or absent).
        "taxonomy_normalizations": taxonomy_entries,
        "flag_unknown_taxonomy": taxonomy_outcome.flag_unknown_taxonomy,
    }
    legacy_err_count = len(dq_report.errors)
    annex_err_count = len(annex_1a_report.errors)
    run_error = (
        None
        if run_status == "success"
        else {
            "code": "DATA_QUALITY_ERRORS",
            "message": (
                f"{legacy_err_count} legacy data-quality error(s) and "
                f"{annex_err_count} Annex 1-A error(s) recorded; "
                "see final_output.data_quality / annex_1a_data_quality."
            ),
        }
    )
    agent_run = AgentRun(
        id=agent_run_id,
        complaint_id=canonical.complaint_id,
        agent_name=_AGENT_NAME,
        agent_version=_AGENT_VERSION,
        started_at=redaction_started_at,
        ended_at=_now(),
        status=run_status,
        tool_calls=[anonymizer_call],
        final_output=final_output,
        error=run_error,
    )
    session.add(agent_run)
    await session.flush()

    # 6. audit chain. All values redacted.
    base_audit_meta: dict[str, Any] = {
        "agent_run_id": agent_run_id,
        "raw_complaint_id": raw_complaint_id,
        "redaction_policy_version": REDACTION_POLICY_VERSION,
        "dq_policy_version": DQ_POLICY_VERSION,
        "demo_scenario": request.demo_scenario,
    }
    audit_actions = [
        ("complaint-received", "complaint", canonical.complaint_id, None),
        (
            "taxonomy-normalized",
            "complaint",
            canonical.complaint_id,
            {
                **base_audit_meta,
                "normalized_count": len(taxonomy_outcome.normalizations),
                "unknown_count": len(taxonomy_outcome.unknown_terms),
                "dictionary_version": TAXONOMY_DICTIONARY_VERSION,
                "flag_unknown_taxonomy": taxonomy_outcome.flag_unknown_taxonomy,
            },
        ),
        (
            "pii-redacted",
            "complaint",
            canonical.complaint_id,
            {
                **base_audit_meta,
                "entity_count_by_kind": entity_counts,
            },
        ),
        (
            "canonical-complaint-persisted",
            "complaint",
            canonical.complaint_id,
            {**base_audit_meta, "source": "api_realtime"},
        ),
        (
            "data-quality-completed",
            "complaint",
            canonical.complaint_id,
            {
                **base_audit_meta,
                "errors": len(dq_report.errors),
                "warnings": len(dq_report.warnings),
                "suggested": len(dq_report.suggested_enrichments),
            },
        ),
        (
            "complaint-triage-emitted",
            "complaint",
            canonical.complaint_id,
            {**base_audit_meta, "sse_topic": "cockpit"},
        ),
    ]
    for action, object_type, object_id, meta in audit_actions:
        # Attach the per-normalization diff to the taxonomy-normalized
        # row so the audit trail carries the (field, original →
        # canonical, dictionary_version) tuple per the prompt contract.
        if action == "taxonomy-normalized":
            row_diff: dict[str, Any] | None = {
                "normalizations": [
                    n.to_audit_diff() for n in taxonomy_outcome.normalizations
                ]
            }
        else:
            row_diff = None
        await record_audit_event(
            session,
            actor_type="agent",
            actor_id=actor_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            diff=row_diff,
            meta=meta or base_audit_meta,
        )

    # 6c. One ``taxonomy-unknown-term`` warning per unrecognised value.
    #     Does not block ingestion — the canonical field already carries
    #     the raw value unchanged and ``flag_unknown_taxonomy`` is set
    #     on the agent_run / SSE envelope.
    for unknown in taxonomy_outcome.unknown_terms:
        await record_audit_event(
            session,
            actor_type="agent",
            actor_id=actor_id,
            action="taxonomy-unknown-term",
            object_type="complaint",
            object_id=canonical.complaint_id,
            diff=unknown.to_audit_diff(),
            meta={
                **base_audit_meta,
                "severity": "warning",
                "dictionary_version": TAXONOMY_DICTIONARY_VERSION,
            },
        )

    # 6b. One ``dq-rule-violated`` row per Annex 1-A DQ result. The
    #     meta carries the structured rule output (rule_id, field_path,
    #     observed_value, expected, severity) per the prompt's audit
    #     contract. observed_value is PII-safe by construction — the
    #     rule layer tags PII-bearing fields with "present" / "absent"
    #     / "invalid-format" instead of the raw value.
    for rule_result in annex_1a_report.results:
        await record_audit_event(
            session,
            actor_type="agent",
            actor_id=actor_id,
            action="dq-rule-violated",
            object_type="complaint",
            object_id=canonical.complaint_id,
            diff=None,
            meta={
                **base_audit_meta,
                "rule_id": rule_result.rule_id,
                "field_path": rule_result.field_path,
                "observed_value": rule_result.observed_value,
                "expected": rule_result.expected,
                "severity": rule_result.severity,
                "policy_version": ANNEX_1A_POLICY_VERSION,
            },
        )

    await session.flush()
    chain_rows = 6  # complaint-received + taxonomy-normalized + 4 existing
    total_audit_rows = (
        chain_rows
        + len(annex_1a_report.results)
        + len(taxonomy_outcome.unknown_terms)
    )
    step(
        "finding_triage_event_emitted",
        f"audit chain x{total_audit_rows} "
        f"({chain_rows} chain + {len(annex_1a_report.results)} dq-rule-violated "
        f"+ {len(taxonomy_outcome.unknown_terms)} taxonomy-unknown-term)",
    )

    # 7. publish SSE complaint.received with the cockpit-card shape.
    cockpit_card_payload = {
        "complaint_id": canonical.complaint_id,
        "institution_id": canonical.institution_id,
        "institution_name": institution_name or canonical.institution_id,
        "received_at": _ts(canonical.received_at or _now()),
        "motivo_code": canonical.motivo_code,
        "product_category": canonical.product_category,
        "severity": (canonical.severity or _SEVERITY_DEFAULT).lower(),
        "description_preview": _description_preview(narrative_result.redacted_text),
        "source": "api_realtime",
        "flag_unknown_taxonomy": taxonomy_outcome.flag_unknown_taxonomy,
    }
    event_id: int | None = None
    try:
        event_id = await get_bus().publish(
            "cockpit",
            "complaint.received",
            json.dumps(cockpit_card_payload, default=str),
        )
    except Exception:  # noqa: BLE001
        # The SSE bus is best-effort; persistence has already succeeded.
        event_id = None

    return DemoIngestionOutcome(
        complaint_id=canonical.complaint_id,
        raw_complaint_id=raw_complaint_id,
        institution_id=canonical.institution_id,
        institution_name=institution_name,
        agent_run_id=agent_run_id,
        event_id=event_id,
        timeline=timeline,
        redaction_diff=redaction_diff_payload,
        data_quality=dq_payload,
        annex_1a_data_quality=annex_1a_payload,
        taxonomy_normalizations=taxonomy_entries,
        flag_unknown_taxonomy=taxonomy_outcome.flag_unknown_taxonomy,
    )
