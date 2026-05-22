"""Cockpit snapshot assembly.

The cockpit reads from the same Postgres the institutional ingestion
writes to. The snapshot returned here is the initial-render payload
the Next.js server component fetches; subsequent updates arrive via
SSE deltas.

Three demo institutions, two demo tiers, one active anomaly are seeded
by WS0 — the cockpit surface here renders them. Cross-source channel
data is illustrative for the May 25 demo (no live INDECOPI / Plavia /
Twitter feeds wired yet) and labelled as such in the response shape.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.agent_run import AgentRun
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.institution import InstitutionRecord

TIER_1_INSTITUTION_ID = "SBS-001234"  # BANCO_DEMO_001
TIER_2_INSTITUTION_ID = "SBS-005678"  # COOPAC_DEMO_002

# Recent-complaints cap per tier panel — demo-grade, not a real
# pagination boundary.
RECENT_LIMIT = 6


async def build_cockpit_snapshot(session: AsyncSession) -> dict[str, Any]:
    """Assemble the full cockpit snapshot for the conduct lens.

    Returns the JSON-serialisable dict the GET /v1/internal/cockpit
    endpoint emits and the SSE ``snapshot`` event carries.
    """

    now = datetime.now(tz=timezone.utc)
    window_24h_start = now - timedelta(hours=24)

    institutions = await _load_institutions(session)
    tier1_panel = await _build_tier_panel(
        session,
        institution_id=TIER_1_INSTITUTION_ID,
        institutions=institutions,
        tier_label="Tier 1",
        descriptor_template="Near-real-time API · {today} today",
        window_start=window_24h_start,
    )
    tier2_panel = await _build_tier_panel(
        session,
        institution_id=TIER_2_INSTITUTION_ID,
        institutions=institutions,
        tier_label="Tier 2",
        descriptor_template="Batch upload · {today} last 28d",
        window_start=now - timedelta(days=28),
    )

    kpis = await _build_kpis(session, window_start=window_24h_start)
    anomalies = await _build_anomalies(session, institutions=institutions)
    cross_source = _build_cross_source_strip(institutions=institutions, anomalies=anomalies)

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "kpis": kpis,
        "tier1": tier1_panel,
        "tier2": tier2_panel,
        "cross_source": cross_source,
        "anomalies": anomalies,
    }


async def _load_institutions(session: AsyncSession) -> dict[str, str]:
    rows = (await session.execute(select(InstitutionRecord))).scalars().all()
    return {row.institution_id: row.display_name for row in rows}


async def _build_tier_panel(
    session: AsyncSession,
    *,
    institution_id: str,
    institutions: dict[str, str],
    tier_label: str,
    descriptor_template: str,
    window_start: datetime,
) -> dict[str, Any]:
    # Window count for the descriptor.
    count_q = (
        select(func.count())
        .select_from(ComplaintRecord)
        .where(ComplaintRecord.institution_id == institution_id)
        .where(ComplaintRecord.received_at >= window_start)
    )
    window_count = (await session.execute(count_q)).scalar_one()

    # Recent complaints (cap).
    recent_q = (
        select(ComplaintRecord)
        .where(ComplaintRecord.institution_id == institution_id)
        .order_by(desc(ComplaintRecord.received_at))
        .limit(RECENT_LIMIT)
    )
    recent_rows = (await session.execute(recent_q)).scalars().all()

    return {
        "tier_label": tier_label,
        "institution_id": institution_id,
        "institution_name": institutions.get(institution_id, institution_id),
        "descriptor": descriptor_template.format(today=window_count),
        "recent": [_complaint_to_card(c) for c in recent_rows],
    }


async def _build_kpis(
    session: AsyncSession, window_start: datetime
) -> dict[str, Any]:
    total_24h_q = (
        select(func.count())
        .select_from(ComplaintRecord)
        .where(ComplaintRecord.received_at >= window_start)
    )
    total_24h = (await session.execute(total_24h_q)).scalar_one()

    # Top institutions by 24h complaint count.
    top_q = (
        select(
            ComplaintRecord.institution_id,
            func.count().label("c"),
        )
        .where(ComplaintRecord.received_at >= window_start)
        .group_by(ComplaintRecord.institution_id)
        .order_by(desc("c"))
        .limit(3)
    )
    top_rows = (await session.execute(top_q)).all()
    institutions = await _load_institutions(session)

    # Active anomaly count (one row per non-resolved anomaly).
    anom_q = (
        select(func.count())
        .select_from(AgentRun)
        .where(AgentRun.agent_name == "cross-source-correlator")
        .where(AgentRun.status == "success")
    )
    anomalies_active = (await session.execute(anom_q)).scalar_one()

    return {
        "complaints_24h": total_24h,
        # Deterministic illustrative sparkline (24 hourly values).
        # When a real time-series table exists, this is replaced by a
        # query. Today the demo wants something that looks like data.
        "complaints_24h_sparkline": _illustrative_sparkline(seed=total_24h or 1),
        "anomalies_active": int(anomalies_active),
        "top_institutions": [
            {
                "institution_id": row.institution_id,
                "institution_name": institutions.get(
                    row.institution_id, row.institution_id
                ),
                "count_24h": int(row.c),
            }
            for row in top_rows
        ],
    }


async def _build_anomalies(
    session: AsyncSession,
    institutions: dict[str, str],
) -> list[dict[str, Any]]:
    """Read active anomalies from cross-source-correlator agent runs.

    The WS0 seed produces one such run for BANCO_DEMO_001 with
    composite_score=0.74 and anomaly_flag=true. Subsequent prompts
    extend this with live agent output.
    """

    rows_q = (
        select(AgentRun)
        .where(AgentRun.agent_name == "cross-source-correlator")
        .where(AgentRun.status == "success")
        .order_by(desc(AgentRun.started_at))
        .limit(10)
    )
    rows = (await session.execute(rows_q)).scalars().all()

    anomalies: list[dict[str, Any]] = []
    for row in rows:
        output = row.final_output or {}
        if not output.get("anomaly_flag"):
            continue
        contributions = output.get("channel_contributions") or []
        # Highest single-channel contribution gives us a severity hint
        # for the demo when the agent doesn't emit one explicitly.
        max_contribution = max(
            (c.get("contribution", 0) for c in contributions), default=0
        )
        severity = (
            "critical"
            if max_contribution > 0.3
            else "high"
            if max_contribution > 0.2
            else "medium"
        )
        anomalies.append(
            {
                "id": str(row.id),
                "institution_id": row.complaint_id.split("-")[0]
                if "-" in row.complaint_id
                else row.complaint_id,
                "institution_name": institutions.get(
                    TIER_1_INSTITUTION_ID, TIER_1_INSTITUTION_ID
                ),
                "complaint_id": row.complaint_id,
                "composite_score": output.get("composite_score"),
                "threshold": output.get("threshold", 0.7),
                "channel_contributions": contributions,
                "severity": severity,
                "fired_at": row.started_at.isoformat(timespec="seconds"),
                "findings_filter": {
                    "institution_id": TIER_1_INSTITUTION_ID,
                    "from": (row.started_at - timedelta(hours=24)).isoformat(
                        timespec="seconds"
                    ),
                },
            }
        )
    return anomalies


def _build_cross_source_strip(
    institutions: dict[str, str],
    anomalies: list[dict[str, Any]],
) -> dict[str, Any]:
    """Five-channel strip across the conduct lens.

    For Prompt 10 the per-channel values are illustrative — there is
    no live INDECOPI / Plavia / social-media ingestion yet. The shape
    here matches what the live ingestion will produce (Part 8) so the
    UI does not change at integration time.
    """

    # Pull from the most recent anomaly's contributions when one exists,
    # so the strip and the anomaly card tell the same story. If no
    # anomaly is active, illustrative defaults (calm-state values).
    baseline = {
        "complaints": (0.42, +0.02),
        "social": (0.31, +0.04),
        "indecopi": (0.38, +0.06),
        "plavia": (0.29, -0.01),
        "internal": (0.22, 0.0),
    }
    contributions_by_channel: dict[str, float] = {}
    if anomalies:
        for c in anomalies[0].get("channel_contributions", []):
            contributions_by_channel[c.get("channel", "")] = c.get("value", 0)

    channels: list[dict[str, Any]] = []
    for key in ("complaints", "social", "indecopi", "plavia", "internal"):
        value = contributions_by_channel.get(key, baseline[key][0])
        delta = baseline[key][1]
        channels.append(
            {
                "key": key,
                "value": round(value, 2),
                "delta_24h": delta,
                "sparkline": _illustrative_sparkline(
                    seed=int(value * 100) or 1, length=12
                ),
            }
        )
    return {
        "is_illustrative": True,  # WS3 honesty flag; flips when live ingestion lands.
        "channels": channels,
    }


def _complaint_to_card(c: ComplaintRecord) -> dict[str, Any]:
    text = c.description_text or ""
    return {
        "complaint_id": c.complaint_id,
        "institution_id": c.institution_id,
        "received_at": c.received_at.isoformat(timespec="seconds"),
        "motivo_code": c.motivo_code,
        "product_category": c.product_category,
        "severity": (c.severity or "MEDIUM").lower(),
        "description_preview": text[:120] + ("…" if len(text) > 120 else ""),
        "source": getattr(c, "source", "api_realtime"),
    }


def _illustrative_sparkline(seed: int, length: int = 24) -> list[float]:
    """Deterministic, label-as-illustrative sparkline.

    Stable for a given seed so two clients viewing the same snapshot
    see the same curve. When time-series ingestion lands (Part 8),
    this helper is removed and the real query takes its place.
    """

    out: list[float] = []
    value = (seed % 17) / 20 + 0.3  # 0.3..1.15
    for i in range(length):
        # Cheap deterministic walk; no randomness.
        wobble = ((seed * (i + 1)) % 7) / 50 - 0.07  # -0.07..+0.06
        value = max(0.05, min(1.5, value + wobble))
        out.append(round(value, 3))
    return out
