#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
"""Boot healthcheck for the configured model provider.

Sends ONE canary tool-call request to whatever ``SBS_API_MODEL_PROVIDER``
selects and reports whether the agent runtime would actually work. Exits
0 on success, 1 on failure — so it drops into a boot script, a compose
healthcheck, or a pre-demo check without wrapping.

    SBS_API_MODEL_PROVIDER=cloud SBS_API_CLOUD_LEGAL_APPROVED=true \
        uv run python scripts/provider_healthcheck.py

Prints the deployment name, model id, and round-trip latency. Never
prints the API key: the provider redacts it from every string it emits.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "api"))


async def _main() -> int:
    from sbs_api.agents.providers.healthcheck import check_provider

    print("== provider_healthcheck.py ==")
    result = await check_provider()
    print(result.render())

    if not result.ok:
        print(
            "\nThe agent pipeline would fail on this host. Fix the provider "
            "configuration above, or select a different "
            "SBS_API_MODEL_PROVIDER (on_prem | cloud | replay).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
