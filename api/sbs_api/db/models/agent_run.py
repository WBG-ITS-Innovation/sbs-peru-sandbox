"""Agent-run ORM model.

The ``agent_runs`` table is the durable execution trace produced by every
agent that processes a complaint. The supervisor UI's Findings drilldown
and Approvals evidence panels read from this table.

The shape of every row is governed by the JSON Schema contract at
``docs/schemas/agent_run.schema.json``; the narrative semantics live at
``docs/schemas/agent_run.md``. The integration test
``tests/integration/test_agent_run_schema.py`` validates seeded rows
against that schema and is the Prompt 10 ↔ Prompt 12 integration gate.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from sbs_api.db.base import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    # Server-assigned UUIDv4 stored as a 36-char string. Stable across
    # retries; a retry of an agent against the same complaint creates a new
    # row.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    complaint_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("complaints.complaint_id"), nullable=False
    )

    # kebab-case stable identifier. The schema permits any
    # kebab-case string; the prose contract enumerates the current
    # set. Part 12 agents: {triage, investigation, synthesis,
    # cross-source-correlator}. Legacy
    # Prompt-10 agents still present in seeded data: {classifier,
    # narrative-drafter, query-author, live-ingestion-orchestrator}.
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)

    # Format: ``<agent_name>-<semver>`` (e.g., ``triage-0.3.1``). The prefix
    # repeats ``agent_name`` deliberately so an exported ``agent_version``
    # string is self-describing in audit reports.
    agent_version: Mapped[str] = mapped_column(String(96), nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Null only while the run is in flight. Set on timeout to the timeout
    # instant.
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # One of {in_progress, success, partial, failed, timeout}. Enforced
    # by check constraint. ``in_progress`` is the in-flight state used
    # by the Part 12 agent runtime; the four terminal states are the
    # original Prompt 10 contract.
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    # Ordered array of tool-call records. Shape governed by the JSON Schema.
    tool_calls: Mapped[list] = mapped_column(JSONB, nullable=False)

    # Agent's structured output. Shape depends on ``agent_name`` — see the
    # per-agent table in ``docs/schemas/agent_run.md``. Null when the run
    # produced no usable output (status='failed' or partial with no result).
    final_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Structured error record ``{code, message, tool_name?}`` when status
    # is partial / failed / timeout. Null on success.
    error: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'success', 'partial', 'failed', 'timeout')",
            name="ck_agent_runs_status",
        ),
        Index(
            "ix_agent_runs_complaint_id_started_at",
            "complaint_id",
            "started_at",
        ),
        Index("ix_agent_runs_status", "status"),
        Index("ix_agent_runs_agent_name_started_at", "agent_name", "started_at"),
    )
