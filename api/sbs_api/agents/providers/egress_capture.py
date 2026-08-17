# SPDX-License-Identifier: Apache-2.0
"""Verification hook: capture the redacted payload that goes to the cloud.

The redaction guarantee is only worth what can be demonstrated about it, and a
unit test over ``redact_messages`` demonstrates the function, not the deployment.
What ``stage-h-full``'s cloud leg needs is the **actual bytes handed to the
transport** by the running API process, so it can plant a DNI, a RUC and an
email in a complaint narrative, submit it over the real signed chain, and assert
that none of the three appear in what left the building.

This hook provides exactly that and nothing more.

**Off by default.** Enabled only by setting ``SBS_API_CLOUD_EGRESS_CAPTURE_PATH``
to a writable path.

**Refused in staging and prod.** The file is a copy of prompt content. It is
post-redaction by construction — so if the redaction layer works it holds no
personal data, and if it does not, that is the bug the file exists to catch —
but a real deployment has no reason to write one, and a verification artefact
that can be switched on in production is a liability. ``environment`` in
(``staging``, ``prod``) logs a warning and writes nothing.

**Post-redaction only.** The capture point is after the redaction sweep, and the
function takes the already-redacted payload. There is deliberately no code path
here that can see the raw messages.
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)

_REFUSED_ENVIRONMENTS = ("staging", "prod")


def capture_redacted_payload(
    *,
    redacted_messages: list[dict[str, Any]],
    entity_counts: dict[str, int],
    complaint_id: str | None,
    agent_name: str | None,
    model_id: str,
) -> None:
    """Append one JSON line describing this outbound call, if capture is on.

    Never raises: a verification hook must not be able to break inference.
    """

    try:
        from sbs_api.config import get_settings

        settings = get_settings()
        path = (settings.cloud_egress_capture_path or "").strip()
        if not path:
            return

        if settings.environment in _REFUSED_ENVIRONMENTS:
            log.warning(
                "cloud.egress.capture_refused",
                extra={
                    "event": "cloud.egress.capture_refused",
                    "environment": settings.environment,
                    "reason": (
                        "SBS_API_CLOUD_EGRESS_CAPTURE_PATH is set but capture is "
                        "refused outside dev/test — nothing was written"
                    ),
                },
            )
            return

        record = {
            "complaint_id": complaint_id,
            "agent_name": agent_name,
            "model_id": model_id,
            "entity_counts": dict(entity_counts),
            # The redacted payload, exactly as it will be sent.
            "redacted_messages": redacted_messages,
        }
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001 — never fail the inference call
        log.warning(
            "cloud.egress.capture_failed",
            extra={
                "event": "cloud.egress.capture_failed",
                "error_type": type(exc).__name__,
                "error": str(exc)[:200],
            },
        )
