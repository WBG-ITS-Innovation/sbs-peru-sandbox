"""Insight-chatbot tool surface (P-RESHAPE-7).

Five business tools + one ops tool. The defense against hallucination is
**tight parameters**, not prompt engineering: every tool validates its
arguments and runs a fixed query — there is no free-form SQL, ever, and
no write tool exists. Tool results carry the row ids they returned + a
query hash so the agent can cite them.

None of the business tools return narrative text — only structured refs
(ids, categories, severities, counts). Per-complaint refs are stripped
when ``aggregate_only`` is set (the Superintendent persona).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.aggregation.detector import PatternType
from sbs_api.db.models.complaint import ComplaintRecord
from sbs_api.db.models.fi_brief import FIBrief
from sbs_api.db.models.indecopi_case import IndecopiCase
from sbs_api.db.models.pattern_detection import PatternDetection
from sbs_api.db.models.social_signal import SocialSignal

_SEVERITY_BANDS = {"HIGH", "MEDIUM", "LOW"}
_PATTERN_TYPES = {pt.value for pt in PatternType}
_QUERY_ROW_CAP = 50


class ToolParamError(ValueError):
    """Raised when a tool's arguments fail validation. The dispatcher
    turns this into a structured tool error, never a crash."""


@dataclass(frozen=True)
class ToolResult:
    tool: str
    parameters: dict[str, Any]
    rows: list[dict[str, Any]]
    row_ids: list[str]
    query_hash: str
    error: str | None = None
    aggregate: bool = False

    def citation(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "parameters": self.parameters,
            "row_ids_returned": self.row_ids,
            "query_hash": self.query_hash,
        }


def _query_hash(tool: str, params: dict[str, Any]) -> str:
    blob = json.dumps({"tool": tool, "params": params}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _parse_dt(value: Any, field_name: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError) as exc:
        raise ToolParamError(f"{field_name} is not a valid ISO datetime") from exc


def _clamp_limit(value: Any) -> int:
    try:
        n = int(value) if value is not None else _QUERY_ROW_CAP
    except (ValueError, TypeError) as exc:
        raise ToolParamError("limit must be an integer") from exc
    return max(1, min(n, _QUERY_ROW_CAP))


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def query_complaints(
    session: AsyncSession, params: dict[str, Any], *, aggregate_only: bool
) -> ToolResult:
    motivo = params.get("motivo_code")
    if motivo is not None and not isinstance(motivo, str):
        raise ToolParamError("motivo_code must be a string")
    institution = params.get("institution_code")
    date_from = _parse_dt(params.get("date_from"), "date_from")
    date_to = _parse_dt(params.get("date_to"), "date_to")
    system_signal = params.get("system_signal")
    limit = _clamp_limit(params.get("limit"))

    stmt = select(ComplaintRecord)
    if institution:
        stmt = stmt.where(ComplaintRecord.institution_id == institution)
    if motivo:
        stmt = stmt.where(ComplaintRecord.motivo_code == motivo)
    if date_from:
        stmt = stmt.where(ComplaintRecord.received_at >= date_from)
    if date_to:
        stmt = stmt.where(ComplaintRecord.received_at <= date_to)
    stmt = stmt.order_by(ComplaintRecord.received_at.desc()).limit(limit)
    records = (await session.execute(stmt)).scalars().all()

    params_norm = {
        "institution_code": institution,
        "motivo_code": motivo,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "system_signal": system_signal,
        "limit": limit,
    }
    qh = _query_hash("query_complaints", params_norm)

    if aggregate_only:
        # Aggregate persona: counts only, never per-complaint refs.
        rows = [{"count": len(records)}]
        return ToolResult(
            "query_complaints", params_norm, rows, [], qh, aggregate=True
        )

    rows = [
        {
            "complaint_id": c.complaint_id,
            "institution_code": c.institution_id,
            "motivo_code": c.motivo_code,
            "captured_at": c.received_at.isoformat() if c.received_at else None,
            # No narrative text — refs only.
        }
        for c in records
    ]
    return ToolResult(
        "query_complaints",
        params_norm,
        rows,
        [c["complaint_id"] for c in rows],
        qh,
    )


async def query_patterns(
    session: AsyncSession, params: dict[str, Any], *, aggregate_only: bool
) -> ToolResult:
    institution = params.get("institution_code")
    motivo = params.get("motivo_code")
    pattern_type = params.get("pattern_type")
    severity_band = params.get("severity_band")
    if pattern_type is not None and pattern_type not in _PATTERN_TYPES:
        raise ToolParamError(f"pattern_type must be one of {sorted(_PATTERN_TYPES)}")
    if severity_band is not None and severity_band not in _SEVERITY_BANDS:
        raise ToolParamError(f"severity_band must be one of {sorted(_SEVERITY_BANDS)}")
    date_from = _parse_dt(params.get("date_from"), "date_from")
    date_to = _parse_dt(params.get("date_to"), "date_to")

    stmt = select(PatternDetection)
    if institution:
        stmt = stmt.where(PatternDetection.institution_code == institution)
    if motivo:
        stmt = stmt.where(PatternDetection.complaint_category == motivo)
    if pattern_type:
        stmt = stmt.where(PatternDetection.pattern_type == pattern_type)
    if severity_band:
        stmt = stmt.where(PatternDetection.severity_band == severity_band)
    if date_from:
        stmt = stmt.where(PatternDetection.detected_at >= date_from)
    if date_to:
        stmt = stmt.where(PatternDetection.detected_at <= date_to)
    stmt = stmt.order_by(PatternDetection.detected_at.desc()).limit(_QUERY_ROW_CAP)
    records = (await session.execute(stmt)).scalars().all()

    params_norm = {
        "institution_code": institution,
        "motivo_code": motivo,
        "pattern_type": pattern_type,
        "severity_band": severity_band,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
    }
    qh = _query_hash("query_patterns", params_norm)
    rows = [
        {
            "pattern_id": p.pattern_id,
            "institution_code": p.institution_code,
            "complaint_category": p.complaint_category,
            "pattern_type": p.pattern_type,
            "severity_band": p.severity_band,
            "severity_score": float(p.severity_score),
            "composite_breakdown": p.composite_breakdown,
        }
        for p in records
    ]
    return ToolResult(
        "query_patterns", params_norm, rows, [r["pattern_id"] for r in rows], qh,
        aggregate=aggregate_only,
    )


async def query_fi_profile(
    session: AsyncSession, params: dict[str, Any], *, aggregate_only: bool
) -> ToolResult:
    institution = params.get("institution_code")
    if not institution or not isinstance(institution, str):
        raise ToolParamError("institution_code is required")

    from sbs_api.db.models.institution import InstitutionRecord
    from sbs_api.peer_risk.cohorts import assign_cohort

    inst = (
        await session.execute(
            select(InstitutionRecord).where(
                InstitutionRecord.institution_id == institution
            )
        )
    ).scalar_one_or_none()
    cohort_id = segment = tier = None
    if inst is not None:
        try:
            c = assign_cohort(
                display_name=inst.display_name,
                tier_classification=inst.tier_classification,
            )
            cohort_id, segment, tier = c.cohort_id, c.segment.value, c.size_tier.value
        except Exception:  # noqa: BLE001
            pass

    pattern_counts = dict(
        (
            await session.execute(
                select(PatternDetection.pattern_type, func.count())
                .where(PatternDetection.institution_code == institution)
                .group_by(PatternDetection.pattern_type)
            )
        ).all()
    )
    brief_counts = dict(
        (
            await session.execute(
                select(FIBrief.status, func.count())
                .where(FIBrief.institution_id == institution)
                .group_by(FIBrief.status)
            )
        ).all()
    )

    params_norm = {"institution_code": institution}
    qh = _query_hash("query_fi_profile", params_norm)
    rows = [
        {
            "institution_code": institution,
            "cohort_id": cohort_id,
            "segment": segment,
            "tier": tier,
            "pattern_counts_by_type": {k: int(v) for k, v in pattern_counts.items()},
            "fi_brief_counts_by_status": {k: int(v) for k, v in brief_counts.items()},
        }
    ]
    return ToolResult(
        "query_fi_profile", params_norm, rows, [institution], qh,
        aggregate=aggregate_only,
    )


async def query_cross_source(
    session: AsyncSession, params: dict[str, Any], *, aggregate_only: bool
) -> ToolResult:
    institution = params.get("institution_code")
    window = params.get("window", "7d")
    if window not in {"7d", "30d"}:
        raise ToolParamError("window must be '7d' or '30d'")
    days = 7 if window == "7d" else 30
    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=days)

    complaint_q = select(func.count()).select_from(ComplaintRecord).where(
        ComplaintRecord.received_at >= cutoff
    )
    indecopi_q = select(func.count()).select_from(IndecopiCase).where(
        IndecopiCase.opened_at >= cutoff
    )
    social_q = select(func.count()).select_from(SocialSignal).where(
        SocialSignal.captured_at >= cutoff
    )
    if institution:
        complaint_q = complaint_q.where(ComplaintRecord.institution_id == institution)
        indecopi_q = indecopi_q.where(IndecopiCase.institution_id == institution)
        social_q = social_q.where(
            SocialSignal.detected_institution_codes.any(institution)
        )

    complaints = (await session.execute(complaint_q)).scalar_one()
    indecopi = (await session.execute(indecopi_q)).scalar_one()
    social = (await session.execute(social_q)).scalar_one()

    params_norm = {"institution_code": institution, "window": window}
    qh = _query_hash("query_cross_source", params_norm)
    rows = [
        {
            "institution_code": institution,
            "window": window,
            "complaint_count": int(complaints),
            "indecopi_count": int(indecopi),
            "social_signal_count": int(social),
        }
    ]
    return ToolResult(
        "query_cross_source", params_norm, rows, [], qh, aggregate=aggregate_only
    )


async def chart_it(
    session: AsyncSession, params: dict[str, Any], *, aggregate_only: bool
) -> ToolResult:
    chart_type = params.get("type")
    if chart_type not in {"bar", "line", "heatmap"}:
        raise ToolParamError("type must be one of bar/line/heatmap")
    x_axis = params.get("x_axis")
    y_axis = params.get("y_axis")
    if not x_axis or not y_axis:
        raise ToolParamError("x_axis and y_axis are required")
    data = params.get("data") or []
    if not isinstance(data, list):
        raise ToolParamError("data must be a list of points")
    spec = {
        "type": chart_type,
        "x_axis": x_axis,
        "y_axis": y_axis,
        "series": params.get("series") or [],
        "data_source": params.get("data_source"),
        "data": data[:200],
    }
    qh = _query_hash("chart_it", {k: spec[k] for k in ("type", "x_axis", "y_axis")})
    # chart_it shapes data the persona already retrieved — it is not a
    # data source, so it carries no row ids of its own.
    return ToolResult("chart_it", spec, [spec], [], qh, aggregate=aggregate_only)


async def ops_query(
    session: AsyncSession, params: dict[str, Any], *, aggregate_only: bool
) -> ToolResult:
    """IT-only telemetry tool. Returns aggregate platform metrics only —
    queue depth proxy, agent run counts, ingestion lag — never a business
    field."""
    metric = params.get("metric", "agent_health")
    if metric not in {"agent_health", "ingestion_lag", "queue_depth"}:
        raise ToolParamError("metric must be agent_health/ingestion_lag/queue_depth")
    from sbs_api.db.models.agent_run import AgentRun

    now = datetime.now(tz=timezone.utc)
    rows: list[dict[str, Any]]
    if metric == "agent_health":
        since = now - timedelta(hours=24)
        counts = dict(
            (
                await session.execute(
                    select(AgentRun.agent_name, func.count())
                    .where(AgentRun.started_at >= since)
                    .group_by(AgentRun.agent_name)
                )
            ).all()
        )
        rows = [{"agent_runs_24h_by_agent": {k: int(v) for k, v in counts.items()}}]
    elif metric == "ingestion_lag":
        last = (
            await session.execute(select(func.max(ComplaintRecord.received_at)))
        ).scalar()
        lag_hours = (now - last).total_seconds() / 3600.0 if last else None
        rows = [{"ingestion_lag_hours": round(lag_hours, 2) if lag_hours else None}]
    else:  # queue_depth
        rows = [{"queue_depth": "unavailable_without_redis"}]

    params_norm = {"metric": metric}
    qh = _query_hash("ops_query", params_norm)
    return ToolResult("ops_query", params_norm, rows, [], qh, aggregate=True)


# ---------------------------------------------------------------------------
# Registry + LLM tool inventory
# ---------------------------------------------------------------------------

TOOL_FUNCS = {
    "query_complaints": query_complaints,
    "query_patterns": query_patterns,
    "query_fi_profile": query_fi_profile,
    "query_cross_source": query_cross_source,
    "chart_it": chart_it,
    "ops_query": ops_query,
}

# JSON-schema-ish tool definitions for the LLM inventory. The dispatcher
# filters this by persona scope before the model sees it.
TOOL_DEFINITIONS: dict[str, dict[str, Any]] = {
    "query_complaints": {
        "description": "List complaint references (ids only, no narrative) by filter.",
        "parameters": {
            "institution_code": "string?",
            "motivo_code": "string?",
            "date_from": "iso8601?",
            "date_to": "iso8601?",
            "system_signal": "bool?",
            "limit": "int<=50",
        },
    },
    "query_patterns": {
        "description": "List detected patterns with severity + composite breakdown.",
        "parameters": {
            "institution_code": "string?",
            "motivo_code": "string?",
            "pattern_type": f"enum{sorted(_PATTERN_TYPES)}?",
            "severity_band": "enum[HIGH,MEDIUM,LOW]?",
            "date_from": "iso8601?",
            "date_to": "iso8601?",
        },
    },
    "query_fi_profile": {
        "description": "Cohort + pattern/brief counts + peer position for one FI.",
        "parameters": {"institution_code": "string (required)"},
    },
    "query_cross_source": {
        "description": "Cross-source signal counts (complaints/indecopi/social).",
        "parameters": {"institution_code": "string?", "window": "enum[7d,30d]"},
    },
    "chart_it": {
        "description": "Shape already-retrieved data into a Recharts chart payload.",
        "parameters": {
            "type": "enum[bar,line,heatmap]",
            "x_axis": "string",
            "y_axis": "string",
            "series": "list?",
            "data": "list",
        },
    },
    "ops_query": {
        "description": "Platform telemetry only (agent health / lag / queue). No business data.",
        "parameters": {"metric": "enum[agent_health,ingestion_lag,queue_depth]"},
    },
}


def tool_inventory(permitted: list[str]) -> list[dict[str, Any]]:
    """Build the LLM-facing tool inventory for the permitted tools only."""
    return [
        {"name": name, **TOOL_DEFINITIONS[name]}
        for name in permitted
        if name in TOOL_DEFINITIONS
    ]


async def dispatch_tool(
    session: AsyncSession,
    *,
    name: str,
    params: dict[str, Any],
    permitted: list[str],
    aggregate_only: bool,
) -> ToolResult:
    """Authoritative tool dispatch. Re-checks scope, validates params,
    runs the fixed query. A scope violation or bad param becomes a
    structured error ToolResult — never a crash, never a write."""
    if name not in permitted:
        return ToolResult(
            name, params, [], [], _query_hash(name, params),
            error="scope_denied: tool not permitted for this persona",
        )
    func_ = TOOL_FUNCS.get(name)
    if func_ is None:
        return ToolResult(
            name, params, [], [], _query_hash(name, params),
            error="unknown_tool",
        )
    try:
        return await func_(session, params or {}, aggregate_only=aggregate_only)
    except ToolParamError as exc:
        return ToolResult(
            name, params, [], [], _query_hash(name, params),
            error=f"invalid_parameters: {exc}",
        )
