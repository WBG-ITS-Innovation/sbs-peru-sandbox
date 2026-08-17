# SPDX-License-Identifier: Apache-2.0
"""Persist one ``cloud_inference_audit`` row per outbound cloud call.

Kept apart from :mod:`sbs_api.agents.providers.egress`, which is a pure
function over the payload, so the redaction pass stays testable without a
database and the provider's dependency on one is visible in a single module.

**Its own transaction, on purpose.** The audit row is committed independently of
whatever agent session is in flight. An egress record that disappeared because
the surrounding agent run rolled back would be an audit trail that omits exactly
the calls made during failed analysis — the ones most worth having. The cost is
that the row survives a rolled-back run, which is the correct direction to fail:
the payload really did go to Azure regardless of what the database later decided
about the run.

**It never blocks the call, and never fails it.** A broken audit sink must not
take out inference, so persistence errors are logged and swallowed. That is a
deliberate trade with a visible consequence: an operator who needs the audit
trail to be provably complete should alert on the log event
``cloud.egress.audit_failed`` rather than assume row-count equals call-count.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

log = logging.getLogger(__name__)


async def record_cloud_egress(
    *,
    complaint_id: str | None,
    agent_name: str | None,
    model_id: str,
    redaction_applied: bool,
    entity_counts: dict[str, int],
    message_count: int,
    redacted_chars: int,
) -> str | None:
    """Write the egress audit row. Returns its id, or None if it could not be
    written.

    Never raises: see the module docstring.
    """

    audit_id = str(uuid.uuid4())
    try:
        # Imported here rather than at module scope: providers/__init__ imports
        # the cloud provider to expose the factory, and a module-level DB
        # import would make constructing *any* provider depend on the database
        # layer importing cleanly.
        from sbs_api.db.models.cloud_inference_audit import CloudInferenceAudit
        from sbs_api.db.session import get_sessionmaker

        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            session.add(
                CloudInferenceAudit(
                    id=audit_id,
                    complaint_id=complaint_id,
                    agent_name=agent_name,
                    model_id=model_id,
                    redaction_applied=redaction_applied,
                    entity_counts=dict(entity_counts),
                    message_count=message_count,
                    redacted_chars=redacted_chars,
                )
            )
            await session.commit()
        return audit_id
    except Exception as exc:  # noqa: BLE001 — must never fail the inference call
        log.error(
            "cloud.egress.audit_failed",
            extra={
                "event": "cloud.egress.audit_failed",
                "complaint_id": complaint_id,
                "agent_name": agent_name,
                "model_id": model_id,
                "redaction_applied": redaction_applied,
                "error_type": type(exc).__name__,
                # str(exc) only — a DB error can quote the row it was inserting,
                # and although this row carries no text, the habit is worth
                # keeping in a module named "audit".
                "error": str(exc)[:300],
            },
        )
        return None


def summarise_for_log(entity_counts: dict[str, int]) -> dict[str, Any]:
    """Counts, and their total, in a shape safe to put in a log line."""

    return {
        "entity_counts": dict(entity_counts),
        "entities_redacted_total": sum(entity_counts.values()),
    }
