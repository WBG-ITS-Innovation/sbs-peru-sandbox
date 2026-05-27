"""Findings list + detail assembly.

The list endpoint serves the /app/findings table. The detail endpoint
serves the /app/findings/:id drilldown — its response carries enough
to render all five WS4 panels (narrative + classification + features
+ agent reasoning + draft narrative).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.agent_run import AgentRun
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.complaint_narrative_draft import ComplaintNarrativeDraft
from sbs_api.db.models.institution import InstitutionRecord
from sbs_api.db.models.pending_approval import PendingApproval

# Supervisors see only their assigned institutions; for the demo this
# is the two seeded conduct institutions. Analyst + Head see everything.
SUPERVISOR_INSTITUTIONS = ("SBS-001234", "SBS-005678")

# Default windows per role for the list view.
DEFAULT_WINDOW_SUPERVISOR = timedelta(hours=24)
DEFAULT_WINDOW_ANALYST = timedelta(days=7)


@dataclass(frozen=True)
class FindingsFilters:
    institution_id: str | None = None
    severity: str | None = None
    source: str | None = None       # "api_realtime" | "batch"
    classification: str | None = None
    confidence_band: str | None = None  # "low" | "medium" | "high"
    from_received_at: datetime | None = None
    to_received_at: datetime | None = None

    def confidence_range(self) -> tuple[float, float] | None:
        if self.confidence_band == "low":
            return (0.0, 0.5)
        if self.confidence_band == "medium":
            return (0.5, 0.8)
        if self.confidence_band == "high":
            return (0.8, 1.0)
        return None


def default_filters_for_role(roles: frozenset[str]) -> FindingsFilters:
    """Role-appropriate defaults the list endpoint applies when no
    explicit filters arrive in the query string."""

    now = datetime.now(tz=timezone.utc)
    if "sbs:conduct:analyst" in roles:
        # Lucía: high-confidence findings last 24 hours.
        return FindingsFilters(
            confidence_band="high",
            from_received_at=now - DEFAULT_WINDOW_SUPERVISOR,
        )
    if "sbs:conduct:supervisor" in roles:
        return FindingsFilters(
            from_received_at=now - DEFAULT_WINDOW_SUPERVISOR,
        )
    # Head + fallback.
    return FindingsFilters(from_received_at=now - DEFAULT_WINDOW_ANALYST)


async def build_findings_list(
    session: AsyncSession,
    *,
    roles: frozenset[str],
    filters: FindingsFilters,
) -> dict[str, Any]:
    """Build the list response — table rows + total + applied filters."""

    stmt = select(ComplaintRecord)

    # Role scoping. Supervisor sees only the conduct institutions; the
    # analyst + head roles see everything.
    if (
        "sbs:conduct:analyst" not in roles
        and "sbs:conduct:head" not in roles
    ):
        stmt = stmt.where(ComplaintRecord.institution_id.in_(SUPERVISOR_INSTITUTIONS))

    if filters.institution_id:
        stmt = stmt.where(ComplaintRecord.institution_id == filters.institution_id)
    if filters.severity:
        stmt = stmt.where(ComplaintRecord.severity == filters.severity.upper())
    if filters.source:
        stmt = stmt.where(ComplaintRecord.source == filters.source)
    if filters.from_received_at:
        stmt = stmt.where(ComplaintRecord.received_at >= filters.from_received_at)
    if filters.to_received_at:
        stmt = stmt.where(ComplaintRecord.received_at <= filters.to_received_at)

    stmt = stmt.order_by(desc(ComplaintRecord.received_at)).limit(50)
    rows = (await session.execute(stmt)).scalars().all()
    institutions = await _load_institutions(session)

    # Load classifier outputs for each complaint to surface
    # classification + confidence on the list rows.
    classifiers_by_complaint = await _load_latest_classifier_outputs(
        session, [c.complaint_id for c in rows]
    )

    items: list[dict[str, Any]] = []
    confidence_range = filters.confidence_range()
    for c in rows:
        clf = classifiers_by_complaint.get(c.complaint_id, {})
        classification = clf.get("label") or "—"
        confidence = clf.get("confidence")

        if filters.classification and classification != filters.classification:
            continue
        if confidence_range and confidence is not None:
            lo, hi = confidence_range
            if not (lo <= confidence < hi):
                continue

        items.append(
            {
                "complaint_id": c.complaint_id,
                "institution_id": c.institution_id,
                "institution_name": institutions.get(
                    c.institution_id, c.institution_id
                ),
                "received_at": c.received_at.isoformat(timespec="seconds"),
                "classification": classification,
                "confidence": confidence,
                "severity": (c.severity or "MEDIUM").lower(),
                "source": getattr(c, "source", "api_realtime"),
                "drafted_by_agent": clf.get("drafted_by_agent", False),
            }
        )

    return {
        "items": items,
        "total": len(items),
        "filters_applied": _serialise_filters(filters),
    }


async def build_finding_detail(
    session: AsyncSession,
    *,
    complaint_id: str,
    roles: frozenset[str],
) -> dict[str, Any] | None:
    """Build the drilldown payload for one complaint. Returns None if
    the complaint does not exist or the caller's roles disallow it."""

    complaint = (
        await session.execute(
            select(ComplaintRecord).where(
                ComplaintRecord.complaint_id == complaint_id
            )
        )
    ).scalar_one_or_none()
    if complaint is None:
        return None

    if (
        "sbs:conduct:analyst" not in roles
        and "sbs:conduct:head" not in roles
        and complaint.institution_id not in SUPERVISOR_INSTITUTIONS
    ):
        return None

    institutions = await _load_institutions(session)
    runs_stmt = (
        select(AgentRun)
        .where(AgentRun.complaint_id == complaint_id)
        .order_by(AgentRun.started_at)
    )
    runs = (await session.execute(runs_stmt)).scalars().all()
    agent_runs_payload = [_serialise_agent_run(r) for r in runs]

    classification = _extract_classification(runs)
    features = _extract_features(runs)
    anonymizer = _extract_anonymizer(runs)
    narrative_draft = _extract_narrative_draft(runs)
    taxonomy_normalizations, taxonomy_dictionary_version = (
        _extract_taxonomy_normalizations(runs)
    )
    executive_summary = _extract_executive_summary(runs)
    anomaly = _extract_anomaly(runs)
    similar_complaints = _extract_similar_complaints(runs)

    latest_draft_row = (
        await session.execute(
            select(ComplaintNarrativeDraft)
            .where(ComplaintNarrativeDraft.complaint_id == complaint_id)
            .order_by(desc(ComplaintNarrativeDraft.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    pending_approval = (
        await session.execute(
            select(PendingApproval)
            .where(PendingApproval.complaint_id == complaint_id)
            .where(PendingApproval.status == "pending")
            .order_by(desc(PendingApproval.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    current_narrative = (
        latest_draft_row.after_text if latest_draft_row else narrative_draft
    )

    return {
        "complaint": {
            "complaint_id": complaint.complaint_id,
            "institution_id": complaint.institution_id,
            "institution_name": institutions.get(
                complaint.institution_id, complaint.institution_id
            ),
            "received_at": complaint.received_at.isoformat(timespec="seconds"),
            "source": getattr(complaint, "source", "api_realtime"),
            "motivo_code": complaint.motivo_code,
            "product_category": complaint.product_category,
            "severity": (complaint.severity or "MEDIUM").lower(),
            "channel": complaint.channel,
            "complainant_age_range": complaint.complainant_age_range,
            "complainant_district": complaint.complainant_district,
            "narrative_text": complaint.description_text,
            "narrative_length": len(complaint.description_text or ""),
            # P11 demo-ready overlay — five Annex 1-A resolution-side
            # fields surfaced to the supervisor UI when the institution
            # sends them. ``descripcion_resolucion`` is the redacted
            # text; raw stays in raw_complaints.
            "fecha_resolucion": (
                complaint.fecha_resolucion.isoformat()
                if getattr(complaint, "fecha_resolucion", None)
                else None
            ),
            "tipo_resolucion": getattr(complaint, "tipo_resolucion", None),
            "descripcion_resolucion": getattr(
                complaint, "descripcion_resolucion", None
            ),
            "estado_reclamo": getattr(complaint, "estado_reclamo", None),
            "monto_pendiente": (
                str(complaint.monto_pendiente)
                if getattr(complaint, "monto_pendiente", None) is not None
                else None
            ),
            "flag_unknown_taxonomy": bool(
                getattr(complaint, "flag_unknown_taxonomy", False)
            ),
        },
        "anonymization": anonymizer,
        "classification": classification,
        "features": features,
        # P11 demo-ui-polish — top-level convenience for the findings
        # taxonomy panel. Extracted from the latest live-ingestion
        # orchestrator agent_run; empty list when nothing was mapped.
        "taxonomy_normalizations": taxonomy_normalizations,
        "taxonomy_dictionary_version": taxonomy_dictionary_version,
        "agent_runs": agent_runs_payload,
        "current_narrative": current_narrative,
        "agent_drafted_narrative": narrative_draft,
        # Part 12 (P12) — executive brief from SynthesisAgent surfaces
        # under the Draft summary panel; null when synthesis has not run.
        "executive_summary": executive_summary,
        # Part 12 — anomaly contributions and similar complaints come
        # from InvestigationAgent.final_output. Older complaints that
        # only have the seeded classifier row return None for both.
        "anomaly": anomaly,
        "similar_complaints": similar_complaints,
        "latest_draft_id": latest_draft_row.id if latest_draft_row else None,
        "pending_approval": (
            {
                "id": pending_approval.id,
                "status": pending_approval.status,
                "created_at": pending_approval.created_at.isoformat(
                    timespec="seconds"
                ),
            }
            if pending_approval
            else None
        ),
    }


# ----------------------------------------------------------------------
# Helpers


async def _load_institutions(session: AsyncSession) -> dict[str, str]:
    rows = (await session.execute(select(InstitutionRecord))).scalars().all()
    return {row.institution_id: row.display_name for row in rows}


async def _load_latest_classifier_outputs(
    session: AsyncSession, complaint_ids: list[str]
) -> dict[str, dict]:
    """For each complaint id, find the latest classifier agent_run with a
    final_output and extract label / confidence. Best-effort: complaints
    without a classifier run still appear on the list, just without a
    classification."""

    if not complaint_ids:
        return {}

    stmt = (
        select(AgentRun)
        .where(AgentRun.complaint_id.in_(complaint_ids))
        .order_by(AgentRun.complaint_id, desc(AgentRun.started_at))
    )
    runs = (await session.execute(stmt)).scalars().all()

    out: dict[str, dict] = {}
    drafted: dict[str, bool] = {}
    for run in runs:
        if run.agent_name == "narrative-drafter" and run.status == "success":
            drafted[run.complaint_id] = True
        # Part 12: investigation produces the draft today.
        if run.agent_name == "investigation" and run.status == "success":
            draft = (run.final_output or {}).get("draft_narrative") or {}
            if draft.get("text"):
                drafted[run.complaint_id] = True
        if run.agent_name == "classifier" and run.complaint_id not in out:
            output = run.final_output or {}
            out[run.complaint_id] = {
                "label": output.get("classification"),
                "confidence": output.get("confidence"),
            }
        # Part 12: triage carries classification under .classification.{label,confidence}.
        if (
            run.agent_name == "triage"
            and run.status == "success"
            and run.complaint_id not in out
        ):
            output = run.final_output or {}
            clf = output.get("classification") or {}
            out[run.complaint_id] = {
                "label": clf.get("label"),
                "confidence": clf.get("confidence"),
            }

    for cid, info in out.items():
        info["drafted_by_agent"] = drafted.get(cid, False)
    for cid in complaint_ids:
        if cid not in out and drafted.get(cid):
            out[cid] = {"drafted_by_agent": True}
    return out


def _serialise_agent_run(run: AgentRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "agent_name": run.agent_name,
        "agent_version": run.agent_version,
        "started_at": run.started_at.isoformat(timespec="seconds"),
        "ended_at": run.ended_at.isoformat(timespec="seconds")
        if run.ended_at
        else None,
        "status": run.status,
        "tool_calls": run.tool_calls or [],
        "final_output": run.final_output,
        "error": run.error,
    }


def _extract_taxonomy_normalizations(
    runs: list[AgentRun],
) -> tuple[list[dict[str, str]], str | None]:
    """Return the taxonomy_normalizations list from the latest ingestion run.

    Reads ``final_output.taxonomy_normalizations`` from the most-recent
    ``live-ingestion-orchestrator`` run. Older complaints (or those
    ingested before the P11 demo-ready overlay) return ``([], None)``.
    """

    for run in reversed(runs):
        if run.agent_name != "live-ingestion-orchestrator":
            continue
        output = run.final_output or {}
        entries = output.get("taxonomy_normalizations") or []
        # Defensive copy so the caller can't mutate the agent_run row.
        normalized = [
            {
                "field_path": str(e.get("field_path", "")),
                "original_value": str(e.get("original_value", "")),
                "canonical_value": str(e.get("canonical_value", "")),
                "dictionary_version": str(e.get("dictionary_version", "")),
            }
            for e in entries
            if isinstance(e, dict)
        ]
        dict_version = (
            normalized[0]["dictionary_version"] if normalized else None
        )
        return normalized, dict_version
    return [], None


def _extract_classification(runs: list[AgentRun]) -> dict[str, Any] | None:
    """Pull the most-recent classification.

    Priority: Part 12 ``triage`` agent → legacy ``classifier`` agent.
    The triage agent stores it under ``final_output.classification``;
    the legacy classifier stored it as flat fields. Either shape gives
    the same UI render.
    """
    for run in reversed(runs):
        if run.agent_name == "triage" and run.final_output:
            clf = run.final_output.get("classification") or {}
            if clf.get("label"):
                return {
                    "label": clf.get("label"),
                    "confidence": clf.get("confidence"),
                    "confidence_degraded": False,
                    "sub_patterns": [],
                    "rank_band": None,
                    "model_version": clf.get("model_id"),
                    "alternatives": clf.get("alternatives") or [],
                    "source_agent": "triage",
                }
        if run.agent_name == "classifier" and run.final_output:
            fo = run.final_output
            return {
                "label": fo.get("classification"),
                "confidence": fo.get("confidence"),
                "confidence_degraded": fo.get("confidence_degraded", False),
                "sub_patterns": fo.get("sub_patterns", []),
                "rank_band": fo.get("rank_band"),
                "model_version": _extract_bert_model_version(run),
                "alternatives": [],
                "source_agent": "classifier",
            }
    return None


def _extract_bert_model_version(run: AgentRun) -> str | None:
    for tc in run.tool_calls or []:
        if tc.get("tool_name") == "bert_classifier":
            out = tc.get("output") or {}
            return out.get("model_version")
    return None


def _extract_features(runs: list[AgentRun]) -> dict[str, Any] | None:
    """Pull the most-recent feature attribution.

    Priority: Part 12 ``investigation`` agent (``feature_attribution``
    in ``final_output``, from the ``rank_features`` tool) → legacy
    ``xgboost_ranker`` tool call. Either shape produces the same UI
    feature-importance render.
    """
    # P12 investigation agent first.
    for run in reversed(runs):
        if run.agent_name == "investigation" and run.final_output:
            attribution = run.final_output.get("feature_attribution") or []
            if attribution:
                return {
                    "score": None,
                    "rank_band": None,
                    "feature_contributions": [
                        {
                            "feature_name": f.get("name"),
                            "contribution": f.get("contribution"),
                            "direction": "positive"
                            if (f.get("contribution") or 0) >= 0
                            else "negative",
                        }
                        for f in attribution
                    ],
                    "model_version": run.final_output.get("feature_model_id"),
                    "source_agent": "investigation",
                }
    for run in reversed(runs):
        for tc in run.tool_calls or []:
            if tc.get("tool_name") == "xgboost_ranker":
                out = tc.get("output")
                if out:
                    return {
                        "score": out.get("score"),
                        "rank_band": out.get("rank_band"),
                        "feature_contributions": out.get("feature_contributions", []),
                        "model_version": out.get("model_version"),
                        "source_agent": "classifier-tool",
                    }
        # P12 — also look at rank_features tool inside any run.
        for tc in run.tool_calls or []:
            if tc.get("tool_name") == "rank_features":
                out = tc.get("output")
                if out:
                    return {
                        "score": None,
                        "rank_band": None,
                        "feature_contributions": [
                            {
                                "feature_name": f.get("name"),
                                "contribution": f.get("contribution"),
                                "direction": "positive"
                                if (f.get("contribution") or 0) >= 0
                                else "negative",
                            }
                            for f in out.get("top_features") or []
                        ],
                        "model_version": out.get("model_id"),
                        "source_agent": "rank_features-tool",
                    }
    return None


def _extract_anonymizer(runs: list[AgentRun]) -> dict[str, Any] | None:
    for run in reversed(runs):
        for tc in run.tool_calls or []:
            if tc.get("tool_name") == "anonymizer":
                out = tc.get("output") or {}
                inp = tc.get("input") or {}
                return {
                    "policy_version": (
                        out.get("policy_version") or inp.get("policy_version")
                    ),
                    "redactions": out.get("redactions", []),
                    "status": tc.get("status"),
                }
    return None


def _extract_narrative_draft(runs: list[AgentRun]) -> str | None:
    """Pull the most-recent draft text.

    Priority: Part 12 ``investigation`` agent (``draft_narrative.text``
    in ``final_output``) → legacy ``narrative-drafter`` agent.
    """
    for run in reversed(runs):
        if run.agent_name == "investigation" and run.final_output:
            draft = run.final_output.get("draft_narrative") or {}
            text = draft.get("text")
            if text:
                return text
    for run in reversed(runs):
        if run.agent_name == "narrative-drafter" and run.final_output:
            return run.final_output.get("draft_text")
    return None


def _extract_executive_summary(runs: list[AgentRun]) -> dict[str, Any] | None:
    """Pull the most-recent SynthesisAgent executive summary."""
    for run in reversed(runs):
        if run.agent_name == "synthesis" and run.final_output:
            summary = run.final_output.get("executive_summary") or {}
            if summary.get("text"):
                return {
                    "text": summary.get("text"),
                    "key_points": summary.get("key_points") or [],
                    "audience": summary.get("audience"),
                    "model_version": summary.get("model_id"),
                }
    return None


def _extract_anomaly(runs: list[AgentRun]) -> dict[str, Any] | None:
    """Pull the most-recent investigation-agent anomaly block."""
    for run in reversed(runs):
        if run.agent_name == "investigation" and run.final_output:
            anomaly = run.final_output.get("anomaly") or {}
            if anomaly.get("composite_score") is not None:
                return anomaly
    return None


def _extract_similar_complaints(runs: list[AgentRun]) -> list[dict[str, Any]]:
    """Pull the most-recent investigation-agent similar-complaint list."""
    for run in reversed(runs):
        if run.agent_name == "investigation" and run.final_output:
            items = run.final_output.get("similar_complaints") or []
            if items:
                return items
    return []


def _serialise_filters(f: FindingsFilters) -> dict[str, Any]:
    return {
        "institution_id": f.institution_id,
        "severity": f.severity,
        "source": f.source,
        "classification": f.classification,
        "confidence_band": f.confidence_band,
        "from_received_at": (
            f.from_received_at.isoformat(timespec="seconds")
            if f.from_received_at
            else None
        ),
        "to_received_at": (
            f.to_received_at.isoformat(timespec="seconds")
            if f.to_received_at
            else None
        ),
    }
