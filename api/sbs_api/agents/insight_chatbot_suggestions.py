"""Persona-suggested chatbot questions (P-RESHAPE-9).

Tuned to each role's actual workflow — the specificity is what makes
them useful, so they are intentionally NOT generic. Keyed by the
canonical role string from :mod:`sbs_api.auth.persona_scopes`. The SBS
IT questions map to the IT-only ``ops_query`` tool (P-RESHAPE-7); the
Conduct/exec questions map to the business query tools.
"""

from __future__ import annotations

from sbs_api.auth.persona_scopes import (
    ROLE_ANALYST,
    ROLE_SBS_IT,
    ROLE_SUPERINTENDENT,
    ROLE_SUPERVISOR,
    ROLE_UNIT_HEAD,
)

PERSONA_SUGGESTED_QUESTIONS: dict[str, list[str]] = {
    ROLE_ANALYST: [
        "Muéstrame las quejas con system_signal en las últimas 24 horas",
        "¿Qué clasificación tuvo la queja {ultimo_complaint_id}?",
        "Lista las quejas pendientes de mi cola asignada",
    ],
    ROLE_SUPERVISOR: [
        "¿Qué patrones esperan mi aprobación?",
        "Resume las quejas de comisiones no divulgadas de esta semana",
        "¿Cuántos avisos a IF se enviaron este mes?",
    ],
    ROLE_UNIT_HEAD: [
        "¿Qué instituciones suben en fraude esta semana?",
        "Muéstrame el heatmap de outliers de percentil >= 90",
        "Resume la actividad sectorial de los últimos 7 días",
    ],
    ROLE_SUPERINTENDENT: [
        "Resume los 3 patrones más críticos de esta semana en lenguaje claro",
        "¿Qué cohortes están en estado AMBER o RED?",
        "¿Hay difusiones sectoriales pendientes de mi co-aprobación?",
    ],
    ROLE_SBS_IT: [
        "¿Qué agentes tienen tasa de éxito < 80% en las últimas 24 horas?",
        "Muéstrame las entregas de webhook fallidas",
        "¿Cuál es el lag de ingesta por institución?",
    ],
}


def suggestions_for_roles(roles: frozenset[str]) -> list[str]:
    """Suggested questions for the caller's home persona.

    Uses the most-privileged role the caller holds (same precedence as
    ``primary_persona``) so a multi-role demo account lands on one list.
    """
    for role in (
        ROLE_UNIT_HEAD,
        ROLE_SUPERVISOR,
        ROLE_ANALYST,
        ROLE_SUPERINTENDENT,
        ROLE_SBS_IT,
    ):
        if role in roles:
            return list(PERSONA_SUGGESTED_QUESTIONS[role])
    return []
