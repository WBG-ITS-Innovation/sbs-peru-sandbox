"""DIValeVale audit persistence (P-RESHAPE-8).

One ``validation_audit`` row per record DIValeVale evaluated. References
ids + codes only — never narrative text — so the PII sentinel holds.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from sbs_api.db.models.validation_audit import ValidationAudit

AGENT_ID = "divalevale"
MODEL_PROVIDER = "onprem"


async def write_audit(
    session: AsyncSession,
    *,
    complaint_id: str | None,
    institution_code: str,
    verdict: str,
    failed_rules: list[str],
    routing_action: str,
    tier: str,
    pass2_invoked: bool = False,
    pass2_recoveries: dict[str, Any] | None = None,
    pass2_model_id: str | None = None,
    batch_id: str | None = None,
    latency_ms: int = 0,
    now: datetime | None = None,
) -> ValidationAudit:
    now = now or datetime.now(tz=timezone.utc)
    row = ValidationAudit(
        audit_id=str(uuid.uuid4()),
        complaint_id=complaint_id,
        institution_code=institution_code,
        received_at=now,
        verdict=verdict,
        pass1_failed_rules=failed_rules,
        pass2_invoked=pass2_invoked,
        pass2_recoveries=pass2_recoveries,
        pass2_model_id=pass2_model_id,
        routing_action=routing_action,
        batch_id=batch_id,
        model_id=AGENT_ID,
        model_provider=MODEL_PROVIDER,
        tier=tier,
        latency_ms=latency_ms,
    )
    session.add(row)
    await session.flush()
    return row
