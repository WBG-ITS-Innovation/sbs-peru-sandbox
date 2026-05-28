"""Agent orchestration state machine.

Flow (per ADR 0001, amended by the May-2026 cockpit reshape):

    complaint-received → run_triage
       └─ if final_output.system_signal is True → run_investigation
           └─ run_synthesis
       └─ otherwise → stop after triage

    aggregation tick → pattern_detections HIGH row →
       run_investigation_from_pattern(pattern_id)
       └─ Investigation produces a structured dossier (no LLM call,
         narrative deferred to Peer Risk Radar — P-RESHAPE-3)

Investigation fires on EITHER trigger. The system_signal path runs
inline on ingestion; the pattern path runs from the aggregation cron
job (``sbs_api.aggregation.tick.aggregation_tick_job``) or from a
direct call in integration tests. Both paths land an ``agent_runs``
row with the same agent_name (``investigation``) so the cockpit can
list them together; ``final_output.trigger_source`` distinguishes
them, and ``final_output.pattern_id`` is set for the pattern path.

Double-fire prevention on the pattern path uses a Postgres advisory
lock keyed on the pattern_id hash. Two concurrent tick workers that
pick up the same HIGH pattern will see one acquire the lock and run,
the other observe ``triggered_investigation == true`` after the lock
is released and skip.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import zlib

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.agents.investigation import (
    PatternContext,
    run_investigation,
    run_investigation_for_pattern,
)
from sbs_api.agents.issue_resurface import evaluate_and_draft
from sbs_api.agents.peer_risk_radar import run_peer_risk_radar
from sbs_api.agents.providers import get_provider
from sbs_api.agents.providers.base import ModelProvider
from sbs_api.agents.synthesis import run_synthesis
from sbs_api.agents.triage import run_triage
from sbs_api.db.models.indecopi_case import IndecopiCase
from sbs_api.db.models.institution import InstitutionRecord
from sbs_api.db.models.pattern_detection import PatternDetection

log = logging.getLogger(__name__)


# Postgres advisory locks take a single bigint key. We derive one from
# the pattern_id (UUID string) via CRC32 + a fixed namespace offset so
# two callers using the same pattern_id always derive the same key.
_ADVISORY_LOCK_NAMESPACE = 0x70617474  # ASCII 'patt'


def _advisory_lock_key(pattern_id: str) -> int:
    return (_ADVISORY_LOCK_NAMESPACE << 32) | zlib.crc32(pattern_id.encode())


@dataclass
class OrchestrationResult:
    triage: dict[str, Any]
    investigation: dict[str, Any] | None
    synthesis: dict[str, Any] | None
    route_to: str
    system_signal: bool
    system_signal_reasons: list[str]


async def run_agent_pipeline(
    session: AsyncSession,
    *,
    complaint_id: str,
    provider: ModelProvider | None = None,
) -> OrchestrationResult:
    """Run the full triage → investigation → synthesis chain.

    Returns the structured outputs for each stage so the caller can
    log or assert against them. Each stage writes its own
    ``agent_runs`` row; the caller is expected to ``commit`` once
    after this returns.
    """
    provider = provider or get_provider()

    triage_out = await run_triage(
        session, complaint_id=complaint_id, provider=provider
    )
    route = triage_out.get("route_to") or "info-only"
    system_signal = bool(triage_out.get("system_signal"))
    system_signal_reasons = list(triage_out.get("system_signal_reasons") or [])

    investigation_out: dict[str, Any] | None = None
    synthesis_out: dict[str, Any] | None = None

    if system_signal:
        investigation_out = await run_investigation(
            session, complaint_id=complaint_id, provider=provider
        )
        synthesis_out = await run_synthesis(
            session, complaint_id=complaint_id, provider=provider
        )
    else:
        log.info(
            "agent pipeline stopping at triage: system_signal=false "
            "route_to=%s complaint=%s",
            route,
            complaint_id,
        )

    return OrchestrationResult(
        triage=triage_out,
        investigation=investigation_out,
        synthesis=synthesis_out,
        route_to=route,
        system_signal=system_signal,
        system_signal_reasons=system_signal_reasons,
    )


async def run_investigation_from_pattern(
    session: AsyncSession,
    *,
    pattern_id: str,
) -> dict[str, Any] | None:
    """Pattern-triggered Investigation entry point.

    Returns the Investigation ``final_output`` dict on fire, or ``None``
    when the pattern is not HIGH or was already triggered (double-fire
    prevention). Acquires a Postgres advisory lock on the pattern_id
    for the duration of the call so two concurrent ticks cannot both
    fire.
    """
    pattern = (
        await session.execute(
            select(PatternDetection).where(
                PatternDetection.pattern_id == pattern_id
            )
        )
    ).scalar_one_or_none()
    if pattern is None:
        log.warning("pattern not found pattern_id=%s", pattern_id)
        return None

    if pattern.severity_band != "HIGH":
        log.info(
            "pattern not HIGH — skipping investigation pattern_id=%s band=%s",
            pattern_id,
            pattern.severity_band,
        )
        return None

    lock_key = _advisory_lock_key(pattern_id)
    # ``pg_try_advisory_xact_lock`` returns true if the lock was acquired
    # at this transaction. A second caller with the same key sees false
    # and steps aside. SQLite (used by some unit tests) has no advisory
    # locks; the helper transparently skips the lock there.
    backend = session.bind.dialect.name if session.bind is not None else ""
    if backend == "postgresql":
        acquired = (
            await session.execute(
                text("SELECT pg_try_advisory_xact_lock(:k)").bindparams(k=lock_key)
            )
        ).scalar()
        if not acquired:
            log.info(
                "pattern advisory lock contended — another worker fired pattern_id=%s",
                pattern_id,
            )
            return None

    # Re-check inside the lock so a worker that committed
    # ``triggered_investigation = true`` just before us is observed.
    await session.refresh(pattern)
    if pattern.triggered_investigation:
        log.info(
            "pattern already triggered investigation — skipping pattern_id=%s",
            pattern_id,
        )
        return None

    # Build the FI profile (lightweight — display name + tier — so the
    # cockpit drilldown does not need a separate query).
    fi = (
        await session.execute(
            select(InstitutionRecord).where(
                InstitutionRecord.institution_id == pattern.institution_code
            )
        )
    ).scalar_one_or_none()
    fi_profile = {
        "institution_id": pattern.institution_code,
        "display_name": fi.display_name if fi is not None else None,
        "tier_classification": getattr(fi, "tier_classification", None),
    }

    # Load INDECOPI cases that contributed to the pattern (optional —
    # only present for CROSS_SOURCE_CORRELATION).
    indecopi_ids = list(pattern.contributing_indecopi_case_ids or [])
    if indecopi_ids:
        # Existence check; the IDs are already stored on the pattern row.
        await session.execute(
            select(IndecopiCase.case_id).where(IndecopiCase.case_id.in_(indecopi_ids))
        )

    context = PatternContext(
        pattern_id=pattern.pattern_id,
        pattern_type=pattern.pattern_type,
        severity_score=float(pattern.severity_score),
        severity_band=pattern.severity_band,
        institution_id=pattern.institution_code,
        complaint_category=pattern.complaint_category,
        contributing_complaint_ids=list(pattern.contributing_complaint_ids),
        contributing_indecopi_case_ids=indecopi_ids,
        composite_breakdown=dict(pattern.composite_breakdown or {}),
        fi_profile=fi_profile,
    )

    investigation_output = await run_investigation_for_pattern(
        session, pattern=context
    )

    # Chain PRR. Failure here does NOT roll back the Investigation row —
    # an evidence-only dossier is still valuable. PRR errors are logged
    # and the dossier stays at evidence-only-v1.
    prr_result = None
    try:
        prr_result = await run_peer_risk_radar(
            session, pattern=context
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "PRR failed for pattern_id=%s — dossier stays evidence-only: %s",
            pattern_id,
            exc,
        )

    # Upgrade dossier to narrative-v1 if PRR succeeded.
    if prr_result is not None:
        investigation_output["dossier_format"] = "narrative-v1"
        investigation_output["peer_risk_analysis"] = {
            "analysis_id": prr_result.analysis_id,
            "cohort_id": prr_result.cohort_id,
            "peer_count": prr_result.peer_count,
            "percentile": prr_result.percentile,
            "z_score": prr_result.z_score,
            "is_outlier": prr_result.is_outlier,
            "sustained_days_above_p90": prr_result.sustained_days_above_p90,
            "forecast": prr_result.forecast,
            "narrative_es": prr_result.narrative_es,
            "narrative_en": prr_result.narrative_en,
            "model_id": prr_result.model_id,
            "model_provider": prr_result.model_provider,
        }
        log.info(
            "dossier upgraded to narrative-v1 pattern_id=%s prr_analysis=%s",
            pattern_id,
            prr_result.analysis_id,
        )

        # Chain Sector Broadcast (P-RESHAPE-6) for fraud-emergence
        # patterns: warn the rest of the cohort. Drafts into
        # AWAITING_DUAL_APPROVAL — never auto-sends. Non-fatal on error.
        if pattern.pattern_type == "FRAUD_EMERGENCE":
            try:
                from sbs_api.agents.sector_broadcast import (
                    evaluate_and_draft_broadcast,
                )

                bdecision = await evaluate_and_draft_broadcast(
                    session, pattern=pattern
                )
                investigation_output["sector_broadcast"] = {
                    "drafted": bdecision.drafted,
                    "reason": bdecision.reason,
                    "broadcast_id": bdecision.broadcast_id,
                    "target_fi_count": len(bdecision.target_fi_codes),
                }
                if bdecision.drafted:
                    log.info(
                        "sector broadcast drafted broadcast_id=%s pattern_id=%s",
                        bdecision.broadcast_id,
                        pattern_id,
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "Sector Broadcast failed for pattern_id=%s: %s",
                    pattern_id,
                    exc,
                )

        # Chain Issue Resurface (P-RESHAPE-4). It evaluates its own
        # trigger conditions (outlier + sustained + cooldown) and only
        # drafts a brief into AWAITING_APPROVAL when all hold. It never
        # auto-sends — a supervisor must approve. Failure is non-fatal.
        try:
            decision = await evaluate_and_draft(
                session, pattern=pattern, peer_risk=prr_result
            )
            investigation_output["fi_brief"] = {
                "drafted": decision.drafted,
                "reason": decision.reason,
                "brief_id": decision.brief_id,
            }
            if decision.drafted:
                log.info(
                    "Issue Resurface drafted brief_id=%s pattern_id=%s",
                    decision.brief_id,
                    pattern_id,
                )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "Issue Resurface failed for pattern_id=%s: %s",
                pattern_id,
                exc,
            )

    # Mark the pattern as triggered + record the agent_run id. Look up
    # the latest investigation run for the anchor complaint within the
    # same transaction; the row we just inserted is the newest.
    from sbs_api.db.models.agent_run import AgentRun

    anchor_complaint_id = context.contributing_complaint_ids[0]
    latest = (
        await session.execute(
            select(AgentRun)
            .where(
                AgentRun.complaint_id == anchor_complaint_id,
                AgentRun.agent_name == "investigation",
            )
            .order_by(AgentRun.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    pattern.triggered_investigation = True
    pattern.investigation_run_id = latest.id if latest is not None else None
    await session.execute(
        update(PatternDetection)
        .where(PatternDetection.pattern_id == pattern_id)
        .values(
            triggered_investigation=True,
            investigation_run_id=pattern.investigation_run_id,
        )
    )
    await session.flush()
    log.info(
        "pattern Investigation fired pattern_id=%s severity=%s",
        pattern_id,
        pattern.severity_score,
    )
    return investigation_output
