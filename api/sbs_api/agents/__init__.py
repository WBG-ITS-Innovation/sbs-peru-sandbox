# SPDX-License-Identifier: Apache-2.0
"""Multi-agent layer.

Three-layer architecture per ADR 0001:
- Agents orchestrate (this module's ``triage``, ``investigation``,
  ``synthesis``, ``cross_source_correlator``).
- Tools execute (``agents.tools``).
- Supervisors approve (existing ``approvals`` package).

Agents never reach the LLM directly: they call through a
:class:`~sbs_api.agents.providers.base.ModelProvider`. The active
provider is selected via the ``SBS_API_MODEL_PROVIDER`` environment
variable (``on_prem`` | ``replay`` | ``mock`` | ``cloud``). The
default is ``on_prem``, which itself falls back to ``mock`` when no
vLLM endpoint is reachable.

The full demo path (BCO-2026-000001) is driven by deterministic
replay fixtures so the demo invariants hold regardless of provider
choice — see ``api/sbs_api/agents/fixtures/replay/``.
"""
