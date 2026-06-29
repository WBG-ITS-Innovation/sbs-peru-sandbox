# SPDX-License-Identifier: Apache-2.0
"""Model-provider factory and re-exports.

Selects the active provider from the ``SBS_API_MODEL_PROVIDER`` env
var. The factory caches a single instance per provider name so
agents in the same process share the same client.
"""

from __future__ import annotations

import logging
import os
from threading import Lock
from typing import Any

from sbs_api.agents.providers.base import (
    ModelProvider,
    ModelResponse,
    ToolCallRequest,
    Usage,
)
from sbs_api.agents.providers.cloud import CloudProvider
from sbs_api.agents.providers.mock import MockProvider
from sbs_api.agents.providers.on_prem import OnPremProvider
from sbs_api.agents.providers.replay import ReplayFixtureMissing, ReplayProvider

log = logging.getLogger(__name__)

__all__ = [
    "ModelProvider",
    "ModelResponse",
    "ToolCallRequest",
    "Usage",
    "OnPremProvider",
    "ReplayProvider",
    "MockProvider",
    "CloudProvider",
    "ReplayFixtureMissing",
    "get_provider",
    "reset_provider_cache",
]

VALID_NAMES = ("on_prem", "replay", "mock", "cloud")

_cache: dict[str, Any] = {}
_lock = Lock()


def _build(name: str) -> ModelProvider:
    if name == "on_prem":
        return OnPremProvider()
    if name == "replay":
        return ReplayProvider()
    if name == "mock":
        return MockProvider()
    if name == "cloud":
        return CloudProvider()
    raise ValueError(
        f"Unknown SBS_API_MODEL_PROVIDER {name!r}; expected one of {VALID_NAMES}"
    )


def _provider_from_settings() -> str | None:
    """Resolve provider name via ``Settings`` so the field is not dead config.

    Returns ``None`` (so the caller falls back to env var / default) if the
    settings module cannot be imported in the current context — which keeps
    the unit tests that exercise this module without booting the full app
    runnable.
    """
    try:
        from sbs_api.config import get_settings  # local import: avoid cycle
    except Exception:  # noqa: BLE001
        return None
    try:
        return get_settings().agents_pipeline_provider
    except Exception:  # noqa: BLE001
        return None


def get_provider(name: str | None = None) -> ModelProvider:
    """Return the cached singleton for ``name``.

    Resolution order: explicit ``name`` arg → ``SBS_API_MODEL_PROVIDER`` env
    var (read directly so test overrides via ``monkeypatch.setenv`` work
    without touching ``Settings``) → ``Settings.agents_pipeline_provider``
    → hardcoded default ``on_prem``.
    """
    chosen = (
        name
        or os.getenv("SBS_API_MODEL_PROVIDER")
        or _provider_from_settings()
        or "on_prem"
    ).lower()
    if chosen not in VALID_NAMES:
        raise ValueError(
            f"Unknown SBS_API_MODEL_PROVIDER {chosen!r}; "
            f"expected one of {VALID_NAMES}"
        )
    with _lock:
        if chosen not in _cache:
            _cache[chosen] = _build(chosen)
        return _cache[chosen]


def reset_provider_cache() -> None:
    """Clear the per-process singleton cache. Test-only hook."""
    with _lock:
        _cache.clear()
