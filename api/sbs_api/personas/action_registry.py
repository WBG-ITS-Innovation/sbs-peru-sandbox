"""Persona action registry — what each persona can DO (P-RESHAPE-8.5).

A small, LOCKED-in-code set of action verbs per persona so no dashboard
is read-only. Keyed by the canonical role string from
:mod:`sbs_api.auth.persona_scopes`.

Each action names the ``scope`` that gates its endpoint and the
``endpoint`` it posts to. Where an endpoint already exists (approvals,
overrides, sector-broadcast co-approval) the registry points at the
existing route — those are NOT reimplemented. The ``scope`` field is the
source of truth the route enforces; the registry mirrors it so the
frontend can grey out an action the caller cannot complete.

Adding a persona or an action requires a code change plus a new test.
"""

from __future__ import annotations

from sbs_api.auth.persona_scopes import (
    COMPLAINT_FLAG,
    COMPLAINT_REQUEST_ENRICHMENT,
    DIGEST_ACK,
    DIGEST_GENERATE,
    EXEC_TASKING,
    FI_BRIEF_APPROVE,
    FI_BRIEF_OVERRIDE,
    FINDINGS_PROPOSE,
    INCIDENT_ANNOTATE,
    OPS_REMEDIATE,
    PATTERN_DEFER,
    PATTERN_DELEGATE,
    ROLE_ANALYST,
    ROLE_SBS_IT,
    ROLE_SUPERINTENDENT,
    ROLE_SUPERVISOR,
    ROLE_UNIT_HEAD,
    SECTOR_BROADCAST_APPROVE_PRIMARY,
    SECTOR_BROADCAST_APPROVE_SECONDARY,
)

PERSONA_ACTIONS: dict[str, list[dict]] = {
    ROLE_ANALYST: [
        {
            "action_id": "propose_pattern",
            "label_es": "Proponer patrón",
            "label_en": "Propose pattern",
            "description_es": "Cuando ves algo que el análisis automático no detectó",
            "description_en": "When you see something the automatic analysis missed",
            "endpoint": "POST /v1/internal/findings/manual",
            "scope": FINDINGS_PROPOSE,
            "requires_rationale_chars": 30,
        },
        {
            "action_id": "flag_complaint_for_review",
            "label_es": "Marcar para revisión",
            "label_en": "Flag for review",
            "endpoint": "POST /v1/complaints/{id}/flag",
            "scope": COMPLAINT_FLAG,
            "requires_rationale_chars": 20,
        },
        {
            "action_id": "request_enrichment",
            "label_es": "Solicitar enriquecimiento",
            "label_en": "Request enrichment",
            "endpoint": "POST /v1/complaints/{id}/request_enrichment",
            "scope": COMPLAINT_REQUEST_ENRICHMENT,
            "requires_rationale_chars": 20,
        },
    ],
    ROLE_SUPERVISOR: [
        {
            "action_id": "approve_fi_brief",
            "label_es": "Aprobar aviso a IF",
            "label_en": "Approve FI brief",
            "endpoint": "POST /v1/internal/fi_briefs/{id}/approve",
            "scope": FI_BRIEF_APPROVE,
            "requires_rationale_chars": 20,
        },
        {
            "action_id": "delegate_pattern",
            "label_es": "Delegar a analista",
            "label_en": "Delegate to analyst",
            "endpoint": "POST /v1/internal/findings/{id}/delegate",
            "scope": PATTERN_DELEGATE,
            "requires_rationale_chars": 30,
        },
        {
            "action_id": "defer_pattern",
            "label_es": "Diferir patrón",
            "label_en": "Defer pattern",
            "endpoint": "POST /v1/internal/findings/{id}/defer",
            "scope": PATTERN_DEFER,
            "requires_rationale_chars": 20,
        },
    ],
    ROLE_UNIT_HEAD: [
        {
            "action_id": "override_supervisor_decision",
            "label_es": "Sobrescribir decisión",
            "label_en": "Override decision",
            # Existing route (P-RESHAPE-5) — not reimplemented.
            "endpoint": "POST /v1/internal/persona/fi_briefs/{id}/override",
            "scope": FI_BRIEF_OVERRIDE,
            "requires_rationale_chars": 50,
        },
        {
            "action_id": "approve_sector_broadcast_primary",
            "label_es": "Aprobar difusión sectorial (primaria)",
            "label_en": "Approve sector broadcast (primary)",
            "endpoint": "POST /v1/internal/sector_broadcast/{id}/approve_primary",
            "scope": SECTOR_BROADCAST_APPROVE_PRIMARY,
            "requires_rationale_chars": 50,
        },
        {
            "action_id": "generate_weekly_digest",
            "label_es": "Generar digest semanal",
            "label_en": "Generate weekly digest",
            "endpoint": "POST /v1/internal/exec/digest/generate",
            "scope": DIGEST_GENERATE,
            "requires_rationale_chars": 0,
        },
    ],
    ROLE_SUPERINTENDENT: [
        {
            "action_id": "approve_sector_broadcast_secondary",
            "label_es": "Co-aprobar difusión sectorial",
            "label_en": "Co-approve sector broadcast",
            "endpoint": "POST /v1/internal/sector_broadcast/{id}/approve_secondary",
            "scope": SECTOR_BROADCAST_APPROVE_SECONDARY,
            "requires_rationale_chars": 50,
        },
        {
            "action_id": "request_deeper_look",
            "label_es": "Pedir análisis profundo",
            "label_en": "Request deeper analysis",
            "description_es": "Asigna a Jefe de Unidad para profundizar en un patrón",
            "description_en": "Assigns the Unit Head to dig deeper into a pattern",
            "endpoint": "POST /v1/internal/exec/tasking",
            "scope": EXEC_TASKING,
            "requires_rationale_chars": 30,
        },
        {
            "action_id": "acknowledge_digest",
            "label_es": "Firmar digest semanal",
            "label_en": "Sign weekly digest",
            "endpoint": "POST /v1/internal/exec/digest/{id}/acknowledge",
            "scope": DIGEST_ACK,
            "requires_rationale_chars": 0,
        },
    ],
    ROLE_SBS_IT: [
        {
            "action_id": "annotate_incident",
            "label_es": "Anotar incidente",
            "label_en": "Annotate incident",
            "endpoint": "POST /v1/internal/ops/incidents",
            "scope": INCIDENT_ANNOTATE,
            "requires_rationale_chars": 20,
        },
        # Remediation actions (P-RESHAPE-9). High-privilege — audited.
        {
            "action_id": "retry_webhook",
            "label_es": "Reintentar webhook fallido",
            "label_en": "Retry failed webhook",
            "endpoint": "POST /v1/internal/ops/webhooks/{delivery_id}/retry",
            "scope": OPS_REMEDIATE,
            "requires_rationale_chars": 20,
        },
        {
            "action_id": "requeue_agent_run",
            "label_es": "Reencolar ejecución",
            "label_en": "Requeue agent run",
            "endpoint": "POST /v1/internal/ops/runs/{run_id}/requeue",
            "scope": OPS_REMEDIATE,
            "requires_rationale_chars": 20,
        },
        {
            "action_id": "circuit_break_ingestion",
            "label_es": "Cortocircuito de ingesta para IF",
            "label_en": "Circuit-break FI ingestion",
            "endpoint": "POST /v1/internal/ops/circuit_breaker/{institution_code}",
            "scope": OPS_REMEDIATE,
            "requires_rationale_chars": 50,
            "description_es": (
                "Pausa la ingestión de una IF específica. Sólo en incidentes graves."
            ),
            "description_en": (
                "Pauses ingestion for a specific FI. Serious incidents only."
            ),
        },
    ],
}


def actions_for_roles(roles: frozenset[str]) -> list[dict]:
    """Union of action descriptors for every role the caller holds, in a
    stable order (registry order, de-duplicated by action_id)."""
    seen: set[str] = set()
    out: list[dict] = []
    for role in (
        ROLE_ANALYST,
        ROLE_SUPERVISOR,
        ROLE_UNIT_HEAD,
        ROLE_SUPERINTENDENT,
        ROLE_SBS_IT,
    ):
        if role not in roles:
            continue
        for action in PERSONA_ACTIONS[role]:
            if action["action_id"] in seen:
                continue
            seen.add(action["action_id"])
            out.append(action)
    return out
