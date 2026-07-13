# SPDX-License-Identifier: Apache-2.0
"""Audit-event ORM model — the cross-screen audit chain.

Every state-changing action in the supervisor UI lands a row here:

* WS2 persona switch and login/logout.
* WS5 approval decisions (approve, approve-with-edits, reject, send-back).
* WS6 queue assignments, narrative edits, finding state transitions.
* Plus agent-side actions: classification published, finding drafted,
  cross-source signal threshold crossed.

The audit screen (WS6) reads from this single table; every screen that
mutates state writes through ``sbs_api.audit.record_audit_event``. If a
new screen invents its own audit-writing path, the audit screen shows
some actions and not others — so the single entrypoint is the contract.

Schema is deliberately loose on ``action``, ``object_type``, ``object_id``
(strings, not enums) because every workstream adds new action vocabulary.
The kebab-case convention is enforced by a check constraint on ``action``
only — operators reading the audit table need stable action codes.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # 'user' (Supervisor, Analyst, Head) or 'agent' (a classifier / drafter run).
    actor_type: Mapped[str] = mapped_column(String(8), nullable=False)

    # User email (e.g., 'supervisor@sandbox.example.com') or agent_run id (UUID string).
    # Not FK-constrained — actors can be external services in future.
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # kebab-case action code. Examples: 'login', 'logout', 'switch-persona',
    # 'approve-finding', 'reject-finding', 'send-back-finding', 'edit-narrative',
    # 'assign-complaint', 'classification-published'.
    action: Mapped[str] = mapped_column(String(64), nullable=False)

    # Type of the object the action operated on: 'session', 'finding',
    # 'approval', 'complaint', 'assignment', 'agent-run'.
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # ID of the affected entity. Not FK-constrained because object_type
    # varies (could reference complaints.complaint_id, agent_runs.id,
    # or a synthetic id like 'session-<uuid>' for ephemeral state).
    object_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # Before/after JSON diff for mutation actions; null for events with
    # no meaningful diff (login, switch-persona without state change).
    diff: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Action-specific metadata: severity, rationale, scope set, etc.
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('user', 'agent')",
            name="ck_audit_events_actor_type",
        ),
        CheckConstraint(
            "action ~ '^[a-z][a-z0-9-]*[a-z0-9]$'",
            name="ck_audit_events_action_kebab",
        ),
        Index("ix_audit_events_created_at", "created_at"),
        Index(
            "ix_audit_events_actor",
            "actor_type",
            "actor_id",
            "created_at",
        ),
        Index(
            "ix_audit_events_object",
            "object_type",
            "object_id",
            "created_at",
        ),
        Index("ix_audit_events_action", "action"),
    )
