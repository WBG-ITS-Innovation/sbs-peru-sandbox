"""Unified agent monitoring (P-RESHAPE-8.5).

One surface over all six agents, persona-shaped:

* ``GET /v1/internal/cockpit/agents`` — the card list.
  - Conduct (analyst/supervisor/unit head): all 6, full telemetry.
  - Superintendent (``agents:read:exec``): the 3 FI-facing character
    cards only, aggregate counts, NO per-run detail.
  - SBS IT (``agents:read``): all 6 with full telemetry but display
    branding stripped — IT operates on agents as system entities.
* ``GET /v1/internal/cockpit/agents/{agent_id}/runs`` — recent runs.
* ``GET /v1/internal/cockpit/agents/{agent_id}/runs/{audit_id}`` — detail.
* ``GET /v1/internal/cockpit/agents/stream`` — SSE status changes.

Telemetry is computed at query time from ``agent_runs``. Lupaman is a
UX composite of two underlying agents (peer-risk-radar + sector-broadcast)
whose runs are merged for display; their rows stay distinct in the table.

This router is registered AFTER the DIValeVale-specific router so a
request to ``/agents/divalevale/runs/{id}`` resolves to that route's
richer validation_audit detail; every other agent_id falls through to
the ``agent_runs`` handlers here.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.agents.registry import AGENT_REGISTRY, fi_facing_agent_ids
from sbs_api.agents.status import (
    compute_status,
    latency_ms,
    model_id_of,
    percentile,
    run_outcome,
    success_rate,
)
from sbs_api.auth.persona_scopes import (
    AGENTS_READ,
    AGENTS_READ_EXEC,
    scopes_for_roles,
)
from sbs_api.db.models.agent_run import AgentRun
from sbs_api.dependencies.db import get_session
from sbs_api.dependencies.persona import (
    assert_no_business_fields,
    is_ops_only,
    requires_any_scope,
    requires_scope,
)
from sbs_api.routes._internal_auth import verify_internal_secret
from sbs_api.sse import get_bus

router = APIRouter(prefix="/internal/cockpit/agents", tags=["Cockpit"])

_AGENTS = requires_scope(AGENTS_READ)
_AGENTS_OR_EXEC = requires_any_scope(AGENTS_READ, AGENTS_READ_EXEC)

_WINDOW_HOURS = {"1h": 1, "24h": 24, "7d": 168}
_STATUS_TOPIC = "agents"
_HEARTBEAT_SECONDS = 25.0


def _window_hours(window: str) -> int:
    return _WINDOW_HOURS.get(window, 24)


async def _load_runs(
    session: AsyncSession, names: set[str], now: datetime, hours: int
) -> dict[str, list[AgentRun]]:
    """Load agent_runs grouped by agent_name. Loads at least 24h so the
    DEGRADED/RUNNING status windows are evaluable regardless of the
    display window."""
    if not names:
        return {}
    load_floor = now - timedelta(hours=max(hours, 24))
    rows = (
        await session.execute(
            select(AgentRun)
            .where(AgentRun.agent_name.in_(names))
            .where(AgentRun.started_at >= load_floor)
            .order_by(AgentRun.started_at.desc())
        )
    ).scalars().all()
    grouped: dict[str, list[AgentRun]] = defaultdict(list)
    for r in rows:
        grouped[r.agent_name].append(r)
    return grouped


def _agent_block(
    agent_id: str,
    runs_all: list[AgentRun],
    *,
    now: datetime,
    hours: int,
    exec_view: bool,
    it_view: bool,
) -> dict[str, Any]:
    entry = AGENT_REGISTRY[agent_id]
    window_floor = now - timedelta(hours=hours)
    window_runs = [r for r in runs_all if r.started_at and r.started_at >= window_floor]
    latencies = [v for v in (latency_ms(r) for r in window_runs) if v is not None]
    last_run_at = max((r.started_at for r in window_runs), default=None)
    rate = success_rate(window_runs)

    block: dict[str, Any] = {
        "agent_id": agent_id,
        "is_fi_facing": entry["is_fi_facing"],
        "status": compute_status(runs_all, now),
        "total_runs_in_window": len(window_runs),
        "success_rate": round(rate, 3) if rate is not None else None,
        "p50_latency_ms": percentile(latencies, 0.50),
        "p95_latency_ms": percentile(latencies, 0.95),
        "last_run_at": (
            last_run_at.isoformat(timespec="seconds") if last_run_at else None
        ),
    }
    if not it_view:
        # IT sees agents as system entities — no character branding.
        block["display_name_es"] = entry["display_name_es"]
        block["display_name_en"] = entry["display_name_en"]
        block["character_avatar_id"] = entry["character_avatar_id"]
        block["tagline_es"] = entry["tagline_es"]
        block["tagline_en"] = entry["tagline_en"]
    if not exec_view:
        # Superintendent gets aggregate counts only — no per-run detail.
        recent = sorted(
            window_runs, key=lambda r: r.started_at or now, reverse=True
        )[:5]
        block["recent_runs"] = [
            {
                "audit_id": r.id,
                "underlying_agent_id": r.agent_name,
                "started_at": (
                    r.started_at.isoformat(timespec="seconds")
                    if r.started_at
                    else None
                ),
                "duration_ms": latency_ms(r),
                "status": run_outcome(r.status),
                "model_id": model_id_of(r),
            }
            for r in recent
        ]
    return block


@router.get(
    "",
    dependencies=[Depends(verify_internal_secret)],
)
async def list_agents(
    window: str = Query(default="24h"),
    roles: frozenset[str] = Depends(_AGENTS_OR_EXEC),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    now = datetime.now(tz=timezone.utc)
    hours = _window_hours(window)
    granted = scopes_for_roles(roles)
    # Reached the list via agents:read:exec only → Superintendent shape.
    exec_view = AGENTS_READ not in granted
    it_view = is_ops_only(roles)

    visible_ids = fi_facing_agent_ids() if exec_view else list(AGENT_REGISTRY.keys())
    names: set[str] = set()
    for aid in visible_ids:
        names.update(AGENT_REGISTRY[aid]["underlying_agent_ids"])
    grouped = await _load_runs(session, names, now, hours)

    agents = []
    for aid in visible_ids:
        runs_all: list[AgentRun] = []
        for name in AGENT_REGISTRY[aid]["underlying_agent_ids"]:
            runs_all.extend(grouped.get(name, []))
        agents.append(
            _agent_block(
                aid,
                runs_all,
                now=now,
                hours=hours,
                exec_view=exec_view,
                it_view=it_view,
            )
        )

    payload = {
        "agents": agents,
        "window": window if window in _WINDOW_HOURS else "24h",
        "computed_at": now.isoformat(timespec="seconds"),
    }
    if it_view:
        # Belt-and-braces: IT must never receive a business field.
        assert_no_business_fields(payload)
    return payload


@router.get(
    "/stream",
    dependencies=[Depends(verify_internal_secret), Depends(_AGENTS)],
)
async def agents_stream(
    request: Request,  # noqa: ARG001 — required so StreamingResponse cancels cleanly
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """SSE stream of agent status changes. Emits one snapshot on connect,
    then ``agent_status_changed`` deltas published to the ``agents`` topic
    by the agent runtime."""
    now = datetime.now(tz=timezone.utc)
    names: set[str] = set()
    for entry in AGENT_REGISTRY.values():
        names.update(entry["underlying_agent_ids"])
    grouped = await _load_runs(session, names, now, 24)
    snapshot = {}
    for aid, entry in AGENT_REGISTRY.items():
        runs_all: list[AgentRun] = []
        for name in entry["underlying_agent_ids"]:
            runs_all.extend(grouped.get(name, []))
        snapshot[aid] = compute_status(runs_all, now)

    async def stream() -> AsyncIterator[bytes]:
        yield _frame_comment("connected").encode("utf-8")
        yield _frame_event(
            0, "agent_status_snapshot", json.dumps(snapshot)
        ).encode("utf-8")

        bus = get_bus()
        subscriber = bus.subscribe(_STATUS_TOPIC, last_event_id=None)
        next_event_task = asyncio.create_task(anext(subscriber))
        try:
            while True:
                done, _pending = await asyncio.wait(
                    {next_event_task}, timeout=_HEARTBEAT_SECONDS
                )
                if next_event_task not in done:
                    yield _frame_comment("heartbeat").encode("utf-8")
                    continue
                try:
                    evt = next_event_task.result()
                except StopAsyncIteration:
                    await asyncio.sleep(0.1)
                    subscriber = bus.subscribe(_STATUS_TOPIC, last_event_id=None)
                    next_event_task = asyncio.create_task(anext(subscriber))
                    continue
                yield _frame_event(evt.id, evt.event, evt.data).encode("utf-8")
                next_event_task = asyncio.create_task(anext(subscriber))
        finally:
            next_event_task.cancel()
            try:
                await subscriber.aclose()
            except Exception:  # noqa: BLE001
                pass

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/{agent_id}/runs",
    dependencies=[Depends(verify_internal_secret)],
)
async def agent_runs_list(
    agent_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    before: datetime | None = Query(default=None),
    roles: frozenset[str] = Depends(_AGENTS),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    entry = AGENT_REGISTRY.get(agent_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown agent")
    names = set(entry["underlying_agent_ids"])
    stmt = select(AgentRun).where(AgentRun.agent_name.in_(names))
    if before is not None:
        stmt = stmt.where(AgentRun.started_at < before)
    stmt = stmt.order_by(AgentRun.started_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()

    it_view = is_ops_only(roles)
    items = [_run_list_item(r, it_view) for r in rows]
    payload = {"agent_id": agent_id, "runs": items, "count": len(items)}
    if it_view:
        assert_no_business_fields(payload)
    return payload


def _run_list_item(r: AgentRun, it_view: bool) -> dict[str, Any]:
    item: dict[str, Any] = {
        "audit_id": r.id,
        "underlying_agent_id": r.agent_name,
        "started_at": (
            r.started_at.isoformat(timespec="seconds") if r.started_at else None
        ),
        "ended_at": r.ended_at.isoformat(timespec="seconds") if r.ended_at else None,
        "duration_ms": latency_ms(r),
        "status": run_outcome(r.status),
        "model_id": model_id_of(r),
    }
    if not it_view:
        item["complaint_id"] = r.complaint_id
    return item


@router.get(
    "/{agent_id}/runs/{audit_id}",
    dependencies=[Depends(verify_internal_secret)],
)
async def agent_run_detail(
    agent_id: str,
    audit_id: str,
    roles: frozenset[str] = Depends(_AGENTS),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    entry = AGENT_REGISTRY.get(agent_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown agent")
    names = set(entry["underlying_agent_ids"])
    row = (
        await session.execute(
            select(AgentRun)
            .where(AgentRun.id == audit_id)
            .where(AgentRun.agent_name.in_(names))
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")

    timing = {
        "audit_id": row.id,
        "underlying_agent_id": row.agent_name,
        "status": run_outcome(row.status),
        "started_at": (
            row.started_at.isoformat(timespec="seconds") if row.started_at else None
        ),
        "ended_at": (
            row.ended_at.isoformat(timespec="seconds") if row.ended_at else None
        ),
        "duration_ms": latency_ms(row),
        "model_id": model_id_of(row),
    }
    if is_ops_only(roles):
        # IT: timing + status + model_id only, no business payload.
        assert_no_business_fields(timing)
        return timing

    # Conduct personas: full detail including narrative where present.
    out = row.final_output if isinstance(row.final_output, dict) else None
    return {
        **timing,
        "complaint_id": row.complaint_id,
        "agent_version": row.agent_version,
        "model_provider": out.get("model_provider") if out else None,
        "tool_calls": row.tool_calls,
        "output": row.final_output,
        "error": row.error,
    }


def _frame_event(event_id: int, event_name: str, data: str) -> str:
    safe = data.replace("\r\n", "\n").replace("\n", "\\n")
    return f"id: {event_id}\nevent: {event_name}\ndata: {safe}\n\n"


def _frame_comment(text: str) -> str:
    return f": {text}\n\n"
