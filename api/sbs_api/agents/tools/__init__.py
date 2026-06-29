# SPDX-License-Identifier: Apache-2.0
"""Tool registry import side-effect surface.

Importing this module registers every tool with the central
registry in :mod:`sbs_api.agents.tools.base`. Agents and the
runtime only need :func:`get_tool`, :func:`tools_for`, and
:func:`execute_tool` from base.
"""

from __future__ import annotations

# Import every tool module so the @register_tool decorators fire.
from sbs_api.agents.tools import (  # noqa: F401
    anomaly,
    classify,
    log_taxonomy,
    narrative,
    queries,
    rank_features,
    similar,
)
from sbs_api.agents.tools.base import (  # noqa: F401
    Tool,
    ToolCallRecord,
    ToolContext,
    execute_tool,
    get_tool,
    list_tools,
    register_tool,
    tools_for,
)

__all__ = [
    "Tool",
    "ToolCallRecord",
    "ToolContext",
    "execute_tool",
    "get_tool",
    "list_tools",
    "register_tool",
    "tools_for",
]
