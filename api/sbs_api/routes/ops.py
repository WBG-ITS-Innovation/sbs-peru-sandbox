"""SBS IT operations telemetry (P-RESHAPE-5, Rosa's persona).

Every endpoint requires the ``ops:read`` scope and returns REAL queries
against the running stack — no mock data. Critically, NO business field
(complaint_id, motivo_code, narrative, …) ever appears in an ops
response; each handler runs ``assert_no_business_fields`` on its payload
before returning so a regression fails loudly.

View-only in v1.
    # DEMO: IT console is view-only. Remediation actions (retry, requeue,
    # circuit-break) deferred to post-demo hardening.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.auth.persona_scopes import OPS_READ
from sbs_api.db.models.agent_run import AgentRun
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.webhook_delivery import WebhookDelivery
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.persona import assert_no_business_fields, requires_scope
from sbs_api.routes._internal_auth import verify_internal_secret

router = APIRouter(prefix="/internal/ops", tags=["Ops"])

_OPS = requires_scope(OPS_READ)

# Agents whose run health the IT console tracks.
_TRACKED_AGENTS = (
    "triage",
    "investigation",
    "synthesis",
    "peer-risk-radar",
    "issue-resurface",
)

# Expected ingestion cadence — illustrative target, not a measured SLA.
_EXPECTED_CADENCE_HOURS = 24


def _lag_band(lag_hours: float) -> str:
    if lag_hours < 2:
        return "GREEN"
    if lag_hours <= 12:
        return "AMBER"
    return "RED"


@router.get(
    "/ingestion_lag",
    dependencies=[Depends(verify_internal_secret), Depends(_OPS)],
)
async def ingestion_lag(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Per-FI most-recent received_at + lag band. institution_id is an
    operational identifier (not a business/PII field), so it is allowed."""
    now = datetime.now(tz=timezone.utc)
    rows = (
        await session.execute(
            select(
                ComplaintRecord.institution_id,
                func.max(ComplaintRecord.received_at),
            ).group_by(ComplaintRecord.institution_id)
        )
    ).all()
    items = []
    for institution_id, last_received in rows:
        if last_received is None:
            continue
        lag_hours = (now - last_received).total_seconds() / 3600.0
        items.append(
            {
                "institution_id": institution_id,
                "last_received_at": last_received.isoformat(timespec="seconds"),
                "expected_cadence_hours": _EXPECTED_CADENCE_HOURS,
                "lag_hours": round(lag_hours, 2),
                "status": _lag_band(lag_hours),
            }
        )
    payload = {"items": items, "generated_at": now.isoformat(timespec="seconds")}
    assert_no_business_fields(payload)
    return payload


@router.get(
    "/agent_health",
    dependencies=[Depends(verify_internal_secret), Depends(_OPS)],
)
async def agent_health(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Per-agent last-run + 24h success rate + p50/p95 latency."""
    now = datetime.now(tz=timezone.utc)
    since = now - timedelta(hours=24)
    items = []
    for agent in _TRACKED_AGENTS:
        runs = (
            await session.execute(
                select(AgentRun)
                .where(AgentRun.agent_name == agent)
                .where(AgentRun.started_at >= since)
            )
        ).scalars().all()
        total = len(runs)
        successes = sum(1 for r in runs if r.status == "success")
        latencies = [
            (r.ended_at - r.started_at).total_seconds() * 1000.0
            for r in runs
            if r.ended_at is not None
        ]
        latencies.sort()

        def _pct(p: float) -> float | None:
            if not latencies:
                return None
            idx = min(len(latencies) - 1, int(p * len(latencies)))
            return round(latencies[idx], 1)

        last_run = max((r.started_at for r in runs), default=None)
        items.append(
            {
                "agent": agent,
                "runs_24h": total,
                "success_rate_24h": round(successes / total, 3) if total else None,
                "last_run_at": last_run.isoformat(timespec="seconds")
                if last_run
                else None,
                "p50_latency_ms": _pct(0.50),
                "p95_latency_ms": _pct(0.95),
            }
        )
    payload = {"items": items, "generated_at": now.isoformat(timespec="seconds")}
    assert_no_business_fields(payload)
    return payload


@router.get(
    "/webhook_health",
    dependencies=[Depends(verify_internal_secret), Depends(_OPS)],
)
async def webhook_health(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Delivery totals + attempt-count histogram + last 10 failures
    (institution_id + sanitised error only — never the payload)."""
    rows = (await session.execute(select(WebhookDelivery))).scalars().all()
    status_counts: Counter[str] = Counter(r.status for r in rows)
    attempt_hist: Counter[int] = Counter(r.attempts for r in rows)

    failures = sorted(
        (r for r in rows if r.status in {"delivery_failed", "DELIVERY_FAILED"}),
        key=lambda r: r.last_attempt_at or r.created_at,
        reverse=True,
    )[:10]
    last_failures = [
        {
            "delivery_id": r.delivery_id,
            "institution_id": r.institution_id,
            "attempts": r.attempts,
            "failure_reason": (r.failure_reason or "")[:200],
        }
        for r in failures
    ]
    payload = {
        "total": len(rows),
        "by_status": dict(status_counts),
        "attempt_histogram": {str(k): v for k, v in sorted(attempt_hist.items())},
        "last_failures": last_failures,
    }
    assert_no_business_fields(payload)
    return payload


@router.get(
    "/queue_depth",
    dependencies=[Depends(verify_internal_secret), Depends(_OPS)],
)
async def queue_depth() -> dict[str, Any]:
    """arq queue depth per queue. Reads Redis if reachable; reports
    ``unavailable`` (not a fabricated number) when it is not — mock data
    is forbidden on the IT surface."""
    depths: dict[str, Any] = {}
    try:
        from sbs_api.workers.arq_pool import get_arq_pool

        pool = await get_arq_pool()
        # arq's default queue key.
        depths["arq:queue"] = await pool.zcard("arq:queue")
    except Exception as exc:  # noqa: BLE001
        depths = {"status": "unavailable", "detail": type(exc).__name__}
    payload = {"queues": depths}
    assert_no_business_fields(payload)
    return payload


@router.get(
    "/model_routing",
    dependencies=[Depends(verify_internal_secret), Depends(_OPS)],
)
async def model_routing(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """On-prem vs cloud inference counts. Cloud MUST be 0 in v1 — this is
    a feature, surfaced with an ADR 0001 pointer."""
    since = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    runs = (
        await session.execute(
            select(AgentRun.final_output).where(AgentRun.started_at >= since)
        )
    ).scalars().all()
    onprem = 0
    cloud = 0
    for fo in runs:
        if not isinstance(fo, dict):
            continue
        provider = (fo.get("model_provider") or "").lower()
        if provider == "cloud":
            cloud += 1
        elif provider in {"onprem", "on_prem", "replay", "mock", "template"}:
            onprem += 1
    payload = {
        "onprem_calls_24h": onprem,
        "cloud_calls_24h": cloud,
        "cloud_expected": 0,
        "note": "Cloud inference is gated on SBS_API_CLOUD_LEGAL_APPROVED (ADR 0001). cloud=0 is expected in v1.",
    }
    assert_no_business_fields(payload)
    return payload


@router.get(
    "/social_health",
    dependencies=[Depends(verify_internal_secret), Depends(_OPS)],
)
async def social_health(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Social ingestion telemetry: per-source signal count (24h),
    ingestion lag, entity-resolution match rate, fraud-indicator counts
    (7d). Aggregate counts only — NO post text, NO institution names."""
    from collections import Counter

    from sbs_api.db.models.social_signal import SocialSignal

    now = datetime.now(tz=timezone.utc)
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)

    rows = (
        await session.execute(
            select(SocialSignal).where(SocialSignal.captured_at >= since_7d)
        )
    ).scalars().all()

    by_source_24h: Counter[str] = Counter()
    last_captured_by_source: dict[str, datetime] = {}
    matched = 0
    fraud_counts: Counter[str] = Counter()
    for r in rows:
        if r.captured_at >= since_24h:
            by_source_24h[r.source] += 1
        prev = last_captured_by_source.get(r.source)
        if prev is None or r.captured_at > prev:
            last_captured_by_source[r.source] = r.captured_at
        if r.detected_institution_codes:
            matched += 1
        for ind in r.detected_fraud_indicators or []:
            fraud_counts[ind] += 1

    total_7d = len(rows)
    lag = {
        source: round((now - ts).total_seconds() / 3600.0, 2)
        for source, ts in last_captured_by_source.items()
    }
    payload = {
        "signal_count_24h_by_source": dict(by_source_24h),
        "ingestion_lag_hours_by_source": lag,
        "entity_resolution_match_rate": (
            round(matched / total_7d, 3) if total_7d else None
        ),
        "fraud_indicator_counts_7d": dict(fraud_counts),
        "total_signals_7d": total_7d,
        "generated_at": now.isoformat(timespec="seconds"),
    }
    # institution names / post text are not included; assert no business
    # field leaked (institution_id is operational + not surfaced here).
    assert_no_business_fields(payload)
    return payload


@router.get(
    "/error_tail",
    dependencies=[Depends(verify_internal_secret), Depends(_OPS)],
)
async def error_tail(
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Recent failed/timeout agent runs — error CODE + agent only.
    Business payloads are stripped: we surface ``error.code`` and the
    agent name, never ``final_output`` or any narrative."""
    rows = (
        await session.execute(
            select(AgentRun)
            .where(AgentRun.status.in_(["failed", "timeout", "partial"]))
            .order_by(AgentRun.started_at.desc())
            .limit(20)
        )
    ).scalars().all()
    items = []
    for r in rows:
        code = None
        if isinstance(r.error, dict):
            code = r.error.get("code")
        items.append(
            {
                "agent": r.agent_name,
                "status": r.status,
                "error_code": code,
                "occurred_at": r.started_at.isoformat(timespec="seconds"),
            }
        )
    payload = {"errors": items}
    assert_no_business_fields(payload)
    return payload
