# SPDX-License-Identifier: Apache-2.0
"""Model-provider factory and re-exports.

Selects the active provider from ``Settings.agents_pipeline_provider``,
which reads either ``SBS_API_MODEL_PROVIDER`` (documented name) or
``SBS_API_AGENTS_PIPELINE_PROVIDER``. Configuration reaches this module
only through ``Settings`` — one seam, per the config module contract.
The factory caches a single instance per provider name so agents in the
same process share the same client.

Selectable at runtime: ``on_prem`` (default, the SBS workstation target),
``cloud`` (Azure OpenAI, behind the legal opt-in), ``replay`` (fixtures
from disk, which log a warning on every request). ``mock`` is accepted
only inside a pytest process — it fabricates tool calls, and outside a
test that is indistinguishable from analysis once written to
``agent_runs``.

Nothing here degrades quietly. An unknown name raises ``ValueError``, a
misconfigured provider raises ``ProviderUnavailableError`` from its own
constructor, and no provider substitutes another's output for its own.
"""

from __future__ import annotations

import logging
from threading import Lock
from typing import Any

from sbs_api.agents.providers.base import (
    ModelProvider,
    ModelResponse,
    ProviderUnavailableError,
    ToolCallRequest,
    Usage,
)
from sbs_api.agents.providers.cloud import CloudProvider
from sbs_api.agents.providers.mock import MockProvider, in_test_process
from sbs_api.agents.providers.on_prem import OnPremProvider
from sbs_api.agents.providers.replay import ReplayFixtureMissing, ReplayProvider

log = logging.getLogger(__name__)

__all__ = [
    "ModelProvider",
    "ModelResponse",
    "ProviderUnavailableError",
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

# Selectable via SBS_API_MODEL_PROVIDER in any process.
VALID_NAMES = ("on_prem", "cloud", "replay")
# Buildable only inside pytest, however it is named. Kept out of
# VALID_NAMES so an operator reading the error message is pointed at the
# three real options.
TEST_ONLY_NAMES = ("mock",)

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
    """Resolve the provider name through ``Settings`` — the only env seam.

    Builds a fresh ``Settings`` rather than calling the ``lru_cache``-d
    ``get_settings``: ``reset_provider_cache()`` is the documented way to
    switch providers mid-process (the demo scripts and the test suite both
    do it), and a cached ``Settings`` would pin the value read at import
    time. ``Settings`` resolves both ``SBS_API_MODEL_PROVIDER`` and
    ``SBS_API_AGENTS_PIPELINE_PROVIDER`` via the field's AliasChoices, so
    this module no longer reads ``os.environ`` itself.

    Returns ``None`` (caller falls back to the default) if the settings
    module cannot be imported in the current context — which keeps the unit
    tests that exercise this module without booting the full app runnable.
    """
    try:
        from sbs_api.config import Settings  # local import: avoid cycle
    except Exception:  # noqa: BLE001
        return None
    try:
        return Settings().agents_pipeline_provider
    except Exception:  # noqa: BLE001
        return None


def get_provider(name: str | None = None) -> ModelProvider:
    """Return the cached singleton for ``name``.

    Resolution order: explicit ``name`` arg →
    ``Settings.agents_pipeline_provider`` (env ``SBS_API_MODEL_PROVIDER``
    or ``SBS_API_AGENTS_PIPELINE_PROVIDER``) → hardcoded default
    ``on_prem``. No step substitutes a working provider for a
    misconfigured one.

    Raises ``ValueError`` for an unknown name, and for ``mock`` outside a
    pytest process.
    """
    chosen = (
        name
        or _provider_from_settings()
        or "on_prem"
    ).lower()
    if chosen in TEST_ONLY_NAMES and not in_test_process():
        raise ValueError(
            f"Provider {chosen!r} is test-only and this is not a pytest "
            "process: it fabricates tool calls that reach agent_runs looking "
            "like analysis. Use 'replay' for deterministic runs (it logs a "
            f"warning per request), or one of {VALID_NAMES}."
        )
    if chosen not in VALID_NAMES and chosen not in TEST_ONLY_NAMES:
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
