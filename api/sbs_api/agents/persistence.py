# SPDX-License-Identifier: Apache-2.0
"""Helpers for writing agent_run rows.

Every agent goes through this module so the row shape stays
contract-aligned with ``docs/schemas/agent_run.schema.json`` and the
existing audit-chain conventions.

The helper writes:
- One ``agent-run-started`` audit row (status=in_progress) and
  an in-flight ``agent_runs`` row.
- One ``agent-run-completed`` audit row on success/partial/failed/timeout
  and updates the ``agent_runs`` row with the final state.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.agents.tools.base import ToolCallRecord
from sbs_api.audit import record_audit_event
from sbs_api.db.models.agent_run import AgentRun

# Whether the DB check constraint allows ``in_progress``. The migration
# extends it; older deployments fall back to ``success`` as the
# placeholder status for the in-flight row.
IN_PROGRESS_STATUS = "in_progress"

# ``model_provider`` for a run that calls no model at all — the
# live-ingestion orchestrator's own row, whose work is the deterministic
# anonymizer and data-quality pass.
#
# This exists so NULL can mean exactly one thing. Until v0.2.0 both "written
# before migration 20260810_0001" and "made no model call" landed as NULL, so
# the provenance filter every operator-facing document prescribes —
# ``model_provider IS NOT NULL`` — silently dropped current successful analysis
# along with the historical rows (docs/audit/2026-08-17-v02-check.md F3).
#
# Recording an actual provider name here instead would be worse: it would put a
# guess into an audit table, claiming a model served a run that never called
# one. The sentinel says "no model call" explicitly, which is both true and
# queryable.
NO_MODEL_CALL = "none"


async def start_agent_run(
    session: AsyncSession,
    *,
    complaint_id: str,
    agent_name: str,
    agent_version: str,
) -> AgentRun:
    """Insert an in-flight ``agent_runs`` row and the start audit event."""
    now = datetime.now(tz=timezone.utc)
    run = AgentRun(
        id=str(uuid.uuid4()),
        complaint_id=complaint_id,
        agent_name=agent_name,
        agent_version=agent_version,
        started_at=now,
        ended_at=None,
        status=IN_PROGRESS_STATUS,
        tool_calls=[],
        final_output=None,
        error=None,
    )
    session.add(run)
    await session.flush()

    await record_audit_event(
        session,
        actor_type="agent",
        actor_id=agent_name,
        action="agent-run-started",
        object_type="complaint",
        object_id=complaint_id,
        meta={"agent_run_id": run.id, "agent_version": agent_version},
    )
    return run


async def finish_agent_run(
    session: AsyncSession,
    *,
    run: AgentRun,
    status: str,
    tool_call_records: list[ToolCallRecord],
    final_output: dict[str, Any] | None,
    error: dict[str, Any] | None = None,
    model_provider: str | None = None,
) -> AgentRun:
    """Update an in-flight row to its terminal state + audit event.

    ``model_provider`` is the provider that actually served the run's model
    calls (``LoopResult.served_by``) — "mock" when OnPremProvider fell back,
    not the configured "on_prem". An agent that makes no model call passes
    :data:`NO_MODEL_CALL` rather than leaving it None, so that NULL in the
    column means only "row predates migration 20260810_0001".

    Left None on the failed-loop paths, where the loop raised before any
    response arrived and the provenance is genuinely unknown — those rows
    carry ``status='failed'``, so a provenance filter over successful
    analysis is unaffected."""
    if status not in ("success", "partial", "failed", "timeout"):
        raise ValueError(f"unsupported agent_run status: {status!r}")
    run.ended_at = datetime.now(tz=timezone.utc)
    run.status = status
    run.tool_calls = [r.to_dict() for r in tool_call_records]
    run.final_output = final_output
    run.error = error
    if model_provider is not None:
        run.model_provider = model_provider
    await session.flush()

    await record_audit_event(
        session,
        actor_type="agent",
        actor_id=run.agent_name,
        action="agent-run-completed",
        object_type="complaint",
        object_id=run.complaint_id,
        meta={
            "agent_run_id": run.id,
            "status": status,
            "tool_call_count": len(tool_call_records),
            "model_provider": model_provider,
        },
    )
    return run
