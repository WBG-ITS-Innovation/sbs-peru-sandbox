"""Agent registry — single source of truth for the cockpit (P-RESHAPE-8.5).

Six agents surface in the unified monitoring view. Three are FI-facing
and carry a friendly character name (DIValeVale, Reclamito, Lupaman);
three are internal and keep technical names (Triage, Investigation,
Insight Chatbot).

Lupaman is a UX-only COMPOSITE of two separate underlying agents
(Peer Risk Radar + Sector Broadcast). The underlying agents stay
separate in code, database, and audit trail — ``underlying_agent_ids``
is the only place the composition lives, and telemetry is aggregated at
read time. Provenance is never collapsed.

The registry is LOCKED in code, not config: adding an agent (and thus a
persona→agent audience mapping, which is security-relevant) requires a
code change plus a new test.

``audience_personas`` uses the canonical role strings from
:mod:`sbs_api.auth.persona_scopes` (e.g. ``sbs:conduct:head``), not the
friendly short names — so any persona-matching logic uses real roles.
"""

from __future__ import annotations

from sbs_api.auth.persona_scopes import (
    ROLE_ANALYST,
    ROLE_SBS_IT,
    ROLE_SUPERINTENDENT,
    ROLE_SUPERVISOR,
    ROLE_UNIT_HEAD,
)

AGENT_REGISTRY: dict[str, dict] = {
    "divalevale": {
        "display_name_es": "DIValeVale",
        "display_name_en": "DIValeVale",
        "character_avatar_id": "divalevale_v1",
        "is_fi_facing": True,
        "audience_personas": [
            ROLE_ANALYST,
            ROLE_SUPERVISOR,
            ROLE_UNIT_HEAD,
            ROLE_SBS_IT,
        ],
        "tagline_es": "Valida cada envío de las instituciones",
        "tagline_en": "Validates every institution submission",
        "underlying_agent_ids": ["divalevale"],
    },
    "reclamito": {
        "display_name_es": "Reclamito",
        "display_name_en": "Reclamito",
        "character_avatar_id": "reclamito_v1",
        "is_fi_facing": True,
        "audience_personas": [
            ROLE_SUPERVISOR,
            ROLE_UNIT_HEAD,
            ROLE_SUPERINTENDENT,
        ],
        "tagline_es": "Envía señales tempranas a las instituciones",
        "tagline_en": "Sends early signals to institutions",
        "underlying_agent_ids": ["issue-resurface"],
    },
    "lupaman": {
        "display_name_es": "Lupaman",
        "display_name_en": "Lupaman",
        "character_avatar_id": "lupaman_v1",
        "is_fi_facing": True,
        "audience_personas": [
            ROLE_SUPERVISOR,
            ROLE_UNIT_HEAD,
            ROLE_SUPERINTENDENT,
        ],
        "tagline_es": "Analiza patrones y alerta al sector",
        "tagline_en": "Analyzes patterns and warns the sector",
        # COMPOSITE: two separate underlying agents.
        "underlying_agent_ids": ["peer-risk-radar", "sector-broadcast"],
    },
    "triage": {
        "display_name_es": "Triage",
        "display_name_en": "Triage",
        "character_avatar_id": None,
        "is_fi_facing": False,
        "audience_personas": [
            ROLE_ANALYST,
            ROLE_SUPERVISOR,
            ROLE_UNIT_HEAD,
            ROLE_SBS_IT,
        ],
        "tagline_es": "Clasifica y enruta cada queja",
        "tagline_en": "Classifies and routes every complaint",
        "underlying_agent_ids": ["triage"],
    },
    "investigation": {
        "display_name_es": "Investigation",
        "display_name_en": "Investigation",
        "character_avatar_id": None,
        "is_fi_facing": False,
        "audience_personas": [
            ROLE_ANALYST,
            ROLE_SUPERVISOR,
            ROLE_UNIT_HEAD,
            ROLE_SBS_IT,
        ],
        "tagline_es": "Investiga patrones y señales del sistema",
        "tagline_en": "Investigates patterns and system signals",
        "underlying_agent_ids": ["investigation"],
    },
    "insight-chatbot": {
        "display_name_es": "Insight Chatbot",
        "display_name_en": "Insight Chatbot",
        "character_avatar_id": None,
        "is_fi_facing": False,
        "audience_personas": [
            ROLE_ANALYST,
            ROLE_SUPERVISOR,
            ROLE_UNIT_HEAD,
            ROLE_SBS_IT,
        ],
        "tagline_es": "Responde preguntas sobre los datos",
        "tagline_en": "Answers questions about the data",
        "underlying_agent_ids": ["insight-chatbot"],
    },
}

# Display-card order is the registry insertion order (FI-facing first).
AGENT_IDS: tuple[str, ...] = tuple(AGENT_REGISTRY.keys())


def underlying_agent_names() -> set[str]:
    """Every ``agent_runs.agent_name`` value referenced by the registry."""
    names: set[str] = set()
    for entry in AGENT_REGISTRY.values():
        names.update(entry["underlying_agent_ids"])
    return names


def fi_facing_agent_ids() -> list[str]:
    return [aid for aid, e in AGENT_REGISTRY.items() if e["is_fi_facing"]]
