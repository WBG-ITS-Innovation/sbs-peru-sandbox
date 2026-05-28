"""Persona scoping for the insight chatbot's tool surface (P-RESHAPE-7).

Scope is enforced at the **tool dispatcher**, before the LLM is shown
the tool inventory: the model literally never sees a tool the persona
cannot use, so it cannot call one. This is the defense — not prompt
engineering.

Each tool declares the set of scopes that grant it; a persona may use a
tool if it holds ANY of those scopes. The Superintendent is additionally
flagged ``aggregate_only`` so tools strip per-complaint detail; combined
with the fact that ``query_complaints`` requires ``complaints:read:detail``
(which the Superintendent lacks), Sergio can never reach a per-complaint
row through the chatbot.
"""

from __future__ import annotations

from sbs_api.auth.persona_scopes import (
    COMPLAINTS_READ_DETAIL,
    OPS_READ,
    PATTERNS_READ,
    PATTERNS_READ_DETAIL,
    PEER_RISK_READ,
    PEER_RISK_READ_EXEC,
    ROLE_SUPERINTENDENT,
    scopes_for_roles,
)

# tool name → scopes that grant it (ANY-of). A tool with an empty set is
# granted to any persona holding at least one *business* read scope (see
# _BUSINESS_READ_SCOPES below) — used by chart_it, which only shapes data
# the persona could already retrieve.
TOOL_REQUIRED_SCOPES: dict[str, frozenset[str]] = {
    "query_complaints": frozenset({COMPLAINTS_READ_DETAIL}),
    "query_patterns": frozenset({PATTERNS_READ, PATTERNS_READ_DETAIL}),
    "query_fi_profile": frozenset(
        {PATTERNS_READ, PATTERNS_READ_DETAIL, PEER_RISK_READ, PEER_RISK_READ_EXEC}
    ),
    "query_cross_source": frozenset({PATTERNS_READ, PATTERNS_READ_DETAIL}),
    "chart_it": frozenset(),  # any business persona
    "ops_query": frozenset({OPS_READ}),
}

_BUSINESS_READ_SCOPES = frozenset(
    {
        COMPLAINTS_READ_DETAIL,
        PATTERNS_READ,
        PATTERNS_READ_DETAIL,
        PEER_RISK_READ,
        PEER_RISK_READ_EXEC,
    }
)

# IT's ops_query is mutually exclusive with the business tools: an
# ops-only persona never gets a business tool, and a business persona
# never gets ops_query.
_OPS_ONLY_TOOLS = frozenset({"ops_query"})
_BUSINESS_TOOLS = frozenset(
    {
        "query_complaints",
        "query_patterns",
        "query_fi_profile",
        "query_cross_source",
        "chart_it",
    }
)


def is_aggregate_only(roles: frozenset[str]) -> bool:
    """The Superintendent persona sees aggregate-only tool output."""
    return ROLE_SUPERINTENDENT in roles


def permitted_tools(roles: frozenset[str]) -> list[str]:
    """The chatbot tool names this persona may use, in a stable order.

    The dispatcher builds the LLM tool inventory from exactly this list,
    so an un-permitted tool is invisible to the model."""
    granted = scopes_for_roles(roles)
    has_ops = OPS_READ in granted
    has_business = bool(granted & _BUSINESS_READ_SCOPES)

    out: list[str] = []
    for tool in (
        "query_complaints",
        "query_patterns",
        "query_fi_profile",
        "query_cross_source",
        "chart_it",
        "ops_query",
    ):
        if tool in _OPS_ONLY_TOOLS:
            # ops_query only for an ops persona that holds NO business scope
            # (Rosa). A business persona never gets ops_query.
            if has_ops and not has_business:
                out.append(tool)
            continue
        # Business tools.
        required = TOOL_REQUIRED_SCOPES[tool]
        if tool == "chart_it":
            if has_business:
                out.append(tool)
            continue
        if granted & required:
            out.append(tool)
    return out


def can_use_tool(roles: frozenset[str], tool_name: str) -> bool:
    """Authoritative dispatcher check — re-evaluated at call time."""
    return tool_name in set(permitted_tools(roles))
