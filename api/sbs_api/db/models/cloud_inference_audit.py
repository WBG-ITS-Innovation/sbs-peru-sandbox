# SPDX-License-Identifier: Apache-2.0
"""Egress audit for cloud inference — one row per outbound cloud model call.

``cloud`` is the only provider that puts complaint content on infrastructure the
authority does not run. This table is the record of that, and it answers the
question a supervisor or an auditor will actually ask: *what left, when, for
which complaint, and was it redacted first?*

**It stores no text — not the raw narrative, and not the redacted one.** A
column holding the redacted prompt would be a second copy of the complaint
sitting in an audit table, subject to the same retention and access questions as
the first, and a column holding the raw prompt would defeat the entire purpose.
What is recorded instead is *counts by entity kind*: enough to show the
redaction pass ran and found what it found, useless as a source of personal
data. Same discipline as ``validation_audit``, which references IDs and codes
only.

``redaction_applied`` is the assertion under audit. It is written from whether
the egress redaction pass actually ran on the payload, not from configuration,
so a future code path that reached the transport without redacting would produce
a row saying so rather than no row at all.

The row is written **before** the HTTP request, because the audited event is the
egress itself, not its success. A call that times out or is rejected still put
the payload on the wire, and the table says so.

No foreign key on ``complaint_id`` on purpose: an egress audit must not be
capable of failing because of a referential problem elsewhere, and the canary
tool-call the boot healthcheck makes carries no complaint at all.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from sbs_api.db.base import Base


class CloudInferenceAudit(Base):
    __tablename__ = "cloud_inference_audit"

    # Server-assigned UUIDv4 as a 36-char string, matching agent_runs.id.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # The complaint whose analysis triggered the call. Nullable: the provider
    # healthcheck's canary tool-call belongs to no complaint. Not a foreign
    # key — see the module docstring.
    complaint_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Which agent's loop made the call, so a row can be tied back to the
    # matching agent_runs row via (complaint_id, agent_name).
    agent_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # The Azure deployment the request was addressed to. Azure routes on
    # deployment name rather than model name, and this is recorded at request
    # time, so it is what we asked for rather than what answered.
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # Whether the egress redaction pass ran over this payload. The claim the
    # table exists to substantiate.
    redaction_applied: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # {kind: count} from the redaction engine — e.g. {"pii_id": 2, "pii_ruc": 1}.
    # Kinds with no detections are omitted, so `{}` means the payload carried
    # nothing the engine recognises. Counts only: never values, never text.
    entity_counts: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )

    # Size of the payload, for volume questions ("how much went out?") that
    # would otherwise tempt someone into storing the text to answer.
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    redacted_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # "What went to the cloud for this complaint?" is the lookup this
        # table exists to serve.
        Index(
            "ix_cloud_inference_audit_complaint_id_created_at",
            "complaint_id",
            "created_at",
        ),
        # "Was anything sent unredacted?" — the compliance sweep.
        Index("ix_cloud_inference_audit_redaction_applied", "redaction_applied"),
    )
