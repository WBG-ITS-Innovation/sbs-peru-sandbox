"""CloudProvider — gated scaffold per ADR 0001.

A cloud-LLM path is plausible for v0.2 but requires legal sign-off
on PII isolation, audit trail, and data residency. Until then the
provider is a hard stop: any attempt to call it raises
``NotImplementedError`` even when ``SBS_API_CLOUD_LEGAL_APPROVED=true``
is set.

The env-gate is intentional theatre — it documents the contract
("cloud is not available without explicit, recorded approval") and
forces a second NotImplementedError so a deployment slip cannot
silently exfiltrate PII through a half-finished implementation.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from sbs_api.agents.providers.base import ModelResponse

log = logging.getLogger(__name__)


def _legal_approved() -> bool:
    return os.getenv("SBS_API_CLOUD_LEGAL_APPROVED", "").lower() in (
        "true",
        "1",
        "yes",
    )


class CloudProvider:
    """Permanently-gated cloud provider scaffold."""

    name = "cloud"

    def __init__(self) -> None:
        if not _legal_approved():
            raise NotImplementedError(
                "CloudProvider is gated: set SBS_API_CLOUD_LEGAL_APPROVED=true "
                "and complete the PII-guard / audit / data-residency review "
                "before instantiation (v0.2 work item, see ADR 0001)."
            )
        log.warning(
            "CloudProvider instantiated with SBS_API_CLOUD_LEGAL_APPROVED=true "
            "but no working implementation exists. Any complete() call will "
            "raise. This branch must not run against production traffic."
        )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        agent_name: str | None = None,
        complaint_id: str | None = None,
    ) -> ModelResponse:
        raise NotImplementedError(
            "Cloud path requires PII guard, audit, residency disclosure — "
            "gated for v0.2."
        )
