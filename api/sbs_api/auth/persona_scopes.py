# SPDX-License-Identifier: Apache-2.0
"""Internal persona RBAC — roles, fine-grained scopes, and the map.

Distinct from :mod:`sbs_api.auth.scopes` (the institution-facing OAuth
scopes per RFC 6749). These scopes gate the *internal* SBS cockpit
surface and are carried on the ``X-SBS-Role`` header the Next.js BFF
forwards from the Keycloak session (ADR 0040 §D7).

Five locked personas (P-RESHAPE-5):

* ``sbs:conduct:analyst``     — Lucía: individual complaint inspection
* ``sbs:conduct:supervisor``  — María: pattern landscape for assigned FIs
* ``sbs:conduct:head``        — Jorge: all patterns, final authority
* ``sbs:superintendent``      — Sergio: executive aggregates only, NO PII
* ``sbs:sbs_it``              — Rosa: platform ops, NO business data

WB_REVIEWER and FI_USER do not exist on this platform.
"""

from __future__ import annotations

# --- Roles ----------------------------------------------------------------

ROLE_ANALYST = "sbs:conduct:analyst"
ROLE_SUPERVISOR = "sbs:conduct:supervisor"
ROLE_UNIT_HEAD = "sbs:conduct:head"
ROLE_SUPERINTENDENT = "sbs:superintendent"
ROLE_SBS_IT = "sbs:sbs_it"

ALL_ROLES: frozenset[str] = frozenset(
    {
        ROLE_ANALYST,
        ROLE_SUPERVISOR,
        ROLE_UNIT_HEAD,
        ROLE_SUPERINTENDENT,
        ROLE_SBS_IT,
    }
)

# Roles explicitly removed in P-RESHAPE-5 — referenced so any lingering
# realm/seed row can be asserted absent.
RETIRED_ROLES: frozenset[str] = frozenset({"sbs:wb_reviewer", "wb_reviewer", "fi_user"})


# --- Scopes ---------------------------------------------------------------

COMPLAINTS_READ_DETAIL = "complaints:read:detail"
COMPLAINTS_READ_AGGREGATE = "complaints:read:aggregate"
PATTERNS_READ = "patterns:read"
PATTERNS_READ_DETAIL = "patterns:read:detail"
FI_BRIEF_APPROVE = "fi_brief:approve"
FI_BRIEF_OVERRIDE = "fi_brief:override"
PEER_RISK_READ = "peer_risk:read"
PEER_RISK_READ_EXEC = "peer_risk:read:exec"
OPS_READ = "ops:read"
AUDIT_READ = "audit:read"
ASSIGNMENT_CREATE = "assignment:create"
ASSIGNMENT_ACK = "assignment:ack"
EXEC_READ = "exec:read"
# Sector-broadcast dual approval (P-RESHAPE-6). The secondary approval is
# the EXPLICIT exception to the Superintendent's otherwise read-only role:
# a sector broadcast is a sector-level policy action, so Sergio may
# co-approve as the second approver. Documented in
# docs/personas/superintendent.md.
SECTOR_BROADCAST_APPROVE_PRIMARY = "sector_broadcast:approve_primary"
SECTOR_BROADCAST_APPROVE_SECONDARY = "sector_broadcast:approve_secondary"
# Insight chatbot (P-RESHAPE-7). Every internal persona may open a chatbot
# session; the tool surface inside is scoped per persona. FI users do not
# exist on this platform, so there is no FI grant.
CHATBOT_USE = "chatbot:use"
# Agent monitoring surface (P-RESHAPE-8). Conduct + IT only — Sergio
# is NOT granted it (his exec view summarizes outcomes, not runtime).
AGENTS_READ = "agents:read"
# Superintendent agent view (P-RESHAPE-8.5). A narrower grant: Sergio
# sees only the FI-facing character cards as aggregate counts, never
# per-run detail. The unified /agents list accepts EITHER agents:read or
# agents:read:exec; the per-run detail endpoint rejects agents:read:exec.
AGENTS_READ_EXEC = "agents:read:exec"

# --- Persona action scopes (P-RESHAPE-8.5) --------------------------------
# Each verb a persona may invoke from its dashboard. Approvals/overrides
# reuse the existing scopes above; these gate the new action endpoints.
FINDINGS_PROPOSE = "findings:propose"           # analyst — propose a pattern
COMPLAINT_FLAG = "complaint:flag"               # analyst — flag for review
COMPLAINT_REQUEST_ENRICHMENT = "complaint:request_enrichment"  # analyst
PATTERN_DELEGATE = "pattern:delegate"           # supervisor — to an analyst
PATTERN_DEFER = "pattern:defer"                 # supervisor — defer a pattern
DIGEST_GENERATE = "digest:generate"             # unit head — weekly digest
DIGEST_ACK = "digest:acknowledge"               # superintendent — sign digest
EXEC_TASKING = "exec:tasking"                   # superintendent — deeper look
INCIDENT_ANNOTATE = "incident:annotate"         # sbs_it — annotate incident
# High-privilege IT remediation (P-RESHAPE-9): retry webhook, requeue agent
# run, circuit-break an FI's ingestion. SBS IT only.
OPS_REMEDIATE = "ops:remediate"

ALL_SCOPES: frozenset[str] = frozenset(
    {
        COMPLAINTS_READ_DETAIL,
        COMPLAINTS_READ_AGGREGATE,
        PATTERNS_READ,
        PATTERNS_READ_DETAIL,
        FI_BRIEF_APPROVE,
        FI_BRIEF_OVERRIDE,
        PEER_RISK_READ,
        PEER_RISK_READ_EXEC,
        OPS_READ,
        AUDIT_READ,
        ASSIGNMENT_CREATE,
        ASSIGNMENT_ACK,
        EXEC_READ,
        SECTOR_BROADCAST_APPROVE_PRIMARY,
        SECTOR_BROADCAST_APPROVE_SECONDARY,
        CHATBOT_USE,
        AGENTS_READ,
        AGENTS_READ_EXEC,
        FINDINGS_PROPOSE,
        COMPLAINT_FLAG,
        COMPLAINT_REQUEST_ENRICHMENT,
        PATTERN_DELEGATE,
        PATTERN_DEFER,
        DIGEST_GENERATE,
        DIGEST_ACK,
        EXEC_TASKING,
        INCIDENT_ANNOTATE,
        OPS_REMEDIATE,
    }
)


# --- Role → scope map (locked) --------------------------------------------

ROLE_SCOPES: dict[str, frozenset[str]] = {
    ROLE_ANALYST: frozenset(
        {
            CHATBOT_USE,
            AGENTS_READ,
            COMPLAINTS_READ_DETAIL,
            COMPLAINTS_READ_AGGREGATE,
            PATTERNS_READ_DETAIL,
            ASSIGNMENT_ACK,
            # Action verbs (P-RESHAPE-8.5).
            FINDINGS_PROPOSE,
            COMPLAINT_FLAG,
            COMPLAINT_REQUEST_ENRICHMENT,
        }
    ),
    ROLE_SUPERVISOR: frozenset(
        {
            CHATBOT_USE,
            AGENTS_READ,
            COMPLAINTS_READ_AGGREGATE,
            PATTERNS_READ,
            PATTERNS_READ_DETAIL,
            FI_BRIEF_APPROVE,
            PEER_RISK_READ,
            ASSIGNMENT_CREATE,
            SECTOR_BROADCAST_APPROVE_PRIMARY,
            # Action verbs (P-RESHAPE-8.5).
            PATTERN_DELEGATE,
            PATTERN_DEFER,
        }
    ),
    ROLE_UNIT_HEAD: frozenset(
        {
            CHATBOT_USE,
            AGENTS_READ,
            COMPLAINTS_READ_DETAIL,
            COMPLAINTS_READ_AGGREGATE,
            PATTERNS_READ,
            PATTERNS_READ_DETAIL,
            FI_BRIEF_APPROVE,
            FI_BRIEF_OVERRIDE,
            PEER_RISK_READ,
            AUDIT_READ,
            ASSIGNMENT_CREATE,
            SECTOR_BROADCAST_APPROVE_PRIMARY,
            SECTOR_BROADCAST_APPROVE_SECONDARY,
            # Action verbs (P-RESHAPE-8.5).
            PATTERN_DELEGATE,
            PATTERN_DEFER,
            DIGEST_GENERATE,
        }
    ),
    ROLE_SUPERINTENDENT: frozenset(
        {
            CHATBOT_USE,
            COMPLAINTS_READ_AGGREGATE,
            PATTERNS_READ,  # summary only — data filter enforces aggregate
            PEER_RISK_READ_EXEC,
            EXEC_READ,
            # EXPLICIT exception to read-only: Sergio may co-approve a
            # sector broadcast as the secondary approver.
            SECTOR_BROADCAST_APPROVE_SECONDARY,
            # Narrowed agent view: FI-facing cards as aggregate counts only.
            AGENTS_READ_EXEC,
            # Action verbs (P-RESHAPE-8.5).
            EXEC_TASKING,
            DIGEST_ACK,
        }
    ),
    ROLE_SBS_IT: frozenset(
        {
            CHATBOT_USE,
            AGENTS_READ,
            OPS_READ,
            AUDIT_READ,
            # Action verbs (P-RESHAPE-8.5).
            INCIDENT_ANNOTATE,
            # High-privilege remediation (P-RESHAPE-9).
            OPS_REMEDIATE,
        }
    ),
}


def scopes_for_roles(roles: frozenset[str]) -> frozenset[str]:
    """Union of scopes granted by every role the caller holds."""
    granted: set[str] = set()
    for role in roles:
        granted |= ROLE_SCOPES.get(role, frozenset())
    return frozenset(granted)


def primary_persona(roles: frozenset[str]) -> str | None:
    """Resolve the caller's home persona from their roles.

    Precedence (most-privileged first) so a multi-role demo account
    lands on the richest home view: unit_head > supervisor > analyst >
    superintendent > sbs_it. Returns None when no known role is held.
    """
    for role in (
        ROLE_UNIT_HEAD,
        ROLE_SUPERVISOR,
        ROLE_ANALYST,
        ROLE_SUPERINTENDENT,
        ROLE_SBS_IT,
    ):
        if role in roles:
            return role
    return None


# Persona → home cockpit route segment (consumed by the BFF router).
PERSONA_HOME_ROUTE: dict[str, str] = {
    ROLE_ANALYST: "analyst",
    ROLE_SUPERVISOR: "supervisor",
    ROLE_UNIT_HEAD: "unit-head",
    ROLE_SUPERINTENDENT: "superintendent",
    ROLE_SBS_IT: "it",
}
