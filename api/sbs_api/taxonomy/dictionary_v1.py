# SPDX-License-Identifier: Apache-2.0
"""Canonical taxonomy dictionary v1 (P11 demo-ready overlay).

The real SBS Annex 1-A sample arrives with inconsistent surface forms
for the same logical value:

* ``"Página web de la empresa"`` (LARGE_ENTITIES, mixed case)
* ``"PAG. WEB DE LA EMPRESA"``  (SMALL_ENTITIES, ALL-CAPS)
* ``"Pag. Web"``               (informal short form)

All three are the ``pagina_web`` channel. The dictionary maps every
known surface form to a canonical kebab-style code so dashboards and
analytics can group institutions consistently. The dictionary is
keyed by *field*: the same surface text means different things in
``canal_ingreso`` vs ``producto``, so we keep the lookup field-aware.

The mapping is intentionally hardcoded for the demo. Production will
load this from a versioned reference table; the
``DICTIONARY_VERSION`` constant pinned in every audit row makes the
transition auditable.

Lookups are case-insensitive and whitespace-collapsed. Unknown values
do not block ingestion — the orchestrator records a
``taxonomy-unknown-term`` warning and writes the raw value through
unchanged, with ``flag_unknown_taxonomy=True`` exposed in the SSE /
agent_run envelope so the supervisor UI can highlight the row.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

DICTIONARY_VERSION = "taxonomy-v1"


# ---------------------------------------------------------------------------
# Canonical maps
# ---------------------------------------------------------------------------

# CANAL applies to four request fields: channel_in (CNL_ING),
# channel_operation (CNL_OPE), canal_comunicacion_ampliacion (CNL_AMP),
# and canal_pago_cliente (CNL_PAC). The dictionary is shared because
# the SBS canal code-list is the same for all four.
_CANAL_MAP: dict[str, str] = {
    "pagina web de la empresa": "pagina_web",
    "pag. web de la empresa": "pagina_web",
    "pag web de la empresa": "pagina_web",
    "pag. web": "pagina_web",
    "pag web": "pagina_web",
    "pagina_web": "pagina_web",
    "via telefonica": "telefono",
    "via telefonica.": "telefono",
    "telefono": "telefono",
    "telefonica": "telefono",
    "oficina": "oficina_o_domicilio",
    "oficinas": "oficina_o_domicilio",
    "domicilio": "oficina_o_domicilio",
    "oficina o domicilio": "oficina_o_domicilio",
    "oficina_o_domicilio": "oficina_o_domicilio",
    "correo electronico": "correo_electronico",
    "por correo": "correo_electronico",
    "correo": "correo_electronico",
    "correo_electronico": "correo_electronico",
    "app movil": "app_movil",
    "app_movil": "app_movil",
    "aplicativo movil": "app_movil",
    "aplicativo_movil": "app_movil",
    "cajero automatico": "cajero",
    "cajeros automaticos": "cajero",
    "cajeros corresponsales": "cajero",
    "cajero": "cajero",
    "billeteras digitales": "billetera_digital",
    "billetera digital": "billetera_digital",
    "billetera_digital": "billetera_digital",
    "plataforma": "plataforma_digital",
    "plataforma digital": "plataforma_digital",
    "plataforma_digital": "plataforma_digital",
    "no existe canal asociado": "no_aplica",
    "no_aplica": "no_aplica",
    "no aplica": "no_aplica",
    "whatsapp": "whatsapp",
}


_PRODUCTO_MAP: dict[str, str] = {
    "credito de consumo": "credito_consumo",
    "credito_consumo": "credito_consumo",
    "creditos a pequenas empresas y microempresas": "credito_pyme",
    "credito_pyme": "credito_pyme",
    "tarjeta de credito": "tarjeta_credito",
    "tarjeta_credito": "tarjeta_credito",
    "cuenta de ahorros": "cuenta_ahorros",
    "cuenta_ahorros": "cuenta_ahorros",
    "cuenta corriente": "cuenta_corriente",
    "cuenta_corriente": "cuenta_corriente",
    "transferencia de fondos": "transferencia",
    "transferencia": "transferencia",
    "servicios varios": "servicios_varios",
    "servicios_varios": "servicios_varios",
    "credito hipotecario": "credito_hipotecario",
    "credito_hipotecario": "credito_hipotecario",
    "cuenta a plazo": "deposito_plazo",
    "deposito a plazo": "deposito_plazo",
    "deposito_plazo": "deposito_plazo",
}


_MOTIVO_MAP: dict[str, str] = {
    "operaciones no reconocidas": "operaciones_no_reconocidas",
    "operaciones_no_reconocidas": "operaciones_no_reconocidas",
    "transacciones no procesadas / mal realizadas": "transacciones_no_procesadas",
    "transacciones no procesadas": "transacciones_no_procesadas",
    "transacciones_no_procesadas": "transacciones_no_procesadas",
    "cobros indebidos": "cobros_indebidos",
    "cobros_indebidos": "cobros_indebidos",
    # Existing demo motivo code mapped to the new canonical form so
    # legacy submissions don't get flagged as unknown.
    "cobro_indebido": "cobros_indebidos",
    "inadecuada o insuficiente informacion": "informacion_insuficiente",
    "informacion_insuficiente": "informacion_insuficiente",
    "problemas relacionados con cajeros": "problemas_cajeros",
    "problemas_cajeros": "problemas_cajeros",
    "error en los datos del usuario": "error_datos_usuario",
    "error en los datos del usuario registrado en la empresa": "error_datos_usuario",
    "error_datos_usuario": "error_datos_usuario",
    "incumplimiento de clausulas": "incumplimiento_clausulas",
    "incumplimiento_clausulas": "incumplimiento_clausulas",
    "disconformidad por no atencion": "disconformidad_no_atencion",
    "disconformidad_no_atencion": "disconformidad_no_atencion",
}


_ESTADO_MAP: dict[str, str] = {
    "atendido": "atendido",
    "en proceso": "en_proceso",
    "en_proceso": "en_proceso",
    "pendiente": "pendiente",
}


_TIPO_RESOLUCION_MAP: dict[str, str] = {
    "a favor del usuario": "favor_usuario",
    "favor_usuario": "favor_usuario",
    "a favor de la entidad": "favor_entidad",
    "favor_entidad": "favor_entidad",
    "a favor del cliente": "favor_usuario",
}


# Field → dictionary lookup. The orchestrator iterates this list so the
# audit ordering and the agent_run payload are deterministic.
FIELD_DICTIONARIES: tuple[tuple[str, dict[str, str]], ...] = (
    ("channel_in", _CANAL_MAP),
    ("channel_operation", _CANAL_MAP),
    ("canal_comunicacion_ampliacion", _CANAL_MAP),
    ("canal_pago_cliente", _CANAL_MAP),
    ("product", _PRODUCTO_MAP),
    ("motive", _MOTIVO_MAP),
    ("status", _ESTADO_MAP),
    ("tipo_resolucion", _TIPO_RESOLUCION_MAP),
)


# ---------------------------------------------------------------------------
# Normalization API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Normalization:
    """One field/value pair that the dictionary mapped to a canonical code.

    The orchestrator emits one ``taxonomy-normalized`` audit row per
    instance — the ``diff`` carries this dict in its
    ``{original_value, canonical_value, field_path, dictionary_version}``
    shape.
    """

    field_path: str
    original_value: str
    canonical_value: str

    def to_audit_diff(self) -> dict[str, str]:
        return {
            "field_path": self.field_path,
            "original_value": self.original_value,
            "canonical_value": self.canonical_value,
            "dictionary_version": DICTIONARY_VERSION,
        }


@dataclass(frozen=True)
class UnknownTerm:
    """One field/value pair that the dictionary did not recognise.

    The orchestrator emits one ``taxonomy-unknown-term`` audit
    warning per instance and flips ``flag_unknown_taxonomy`` on the
    agent_run / SSE envelope.
    """

    field_path: str
    original_value: str

    def to_audit_diff(self) -> dict[str, str]:
        return {
            "field_path": self.field_path,
            "original_value": self.original_value,
            "dictionary_version": DICTIONARY_VERSION,
        }


@dataclass
class NormalizationOutcome:
    """Result of normalising every dictionary-backed field on a payload."""

    canonical: dict[str, str] = field(default_factory=dict)
    normalizations: list[Normalization] = field(default_factory=list)
    unknown_terms: list[UnknownTerm] = field(default_factory=list)
    flag_unknown_taxonomy: bool = False

    def to_agent_run_entries(self) -> list[dict[str, str]]:
        return [n.to_audit_diff() for n in self.normalizations]


def _lookup_key(value: str) -> str:
    """Return the case-insensitive, accent-stripped, whitespace-collapsed key.

    The same surface form arrives with NFC / NFD accents (``Página`` vs
    ``Página`` with a combining acute), with extra whitespace, and in
    any case. We strip diacritics, lower-case, and collapse runs of
    whitespace so ``"Página web de la empresa"`` and ``"PAGINA  WEB DE
    LA EMPRESA"`` both hash to ``"pagina web de la empresa"``.
    """

    if not value:
        return ""
    nfd = unicodedata.normalize("NFD", value)
    stripped = "".join(c for c in nfd if not unicodedata.combining(c))
    collapsed = re.sub(r"\s+", " ", stripped).strip().lower()
    return collapsed


def normalize_value(field_path: str, value: str, mapping: dict[str, str]) -> str | None:
    """Return the canonical code for ``value`` in ``mapping``, or None.

    Returns ``None`` if the value is empty or unrecognised; the caller
    decides whether to emit a normalization (mapped, value changed),
    skip (mapped, value unchanged — already canonical), or warn
    (unmapped).
    """

    key = _lookup_key(value)
    if not key:
        return None
    return mapping.get(key)


def normalize_payload(payload: dict[str, Any]) -> NormalizationOutcome:
    """Run every field dictionary against ``payload``.

    ``payload`` is the demo / sandbox submission as a dict (typically
    the output of ``DemoSubmissionRequest.model_dump()``). Returns a
    :class:`NormalizationOutcome` listing every (field, original ->
    canonical) pair the dictionary mapped, plus every (field, value)
    pair it did not recognise. The caller is responsible for emitting
    the audit rows and updating the canonical complaint row.
    """

    outcome = NormalizationOutcome()
    for field_path, mapping in FIELD_DICTIONARIES:
        raw = payload.get(field_path)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        if not isinstance(raw, str):
            # Non-string values (e.g. numeric amounts) are not subject
            # to taxonomy normalization. Skip silently.
            continue

        canonical = normalize_value(field_path, raw, mapping)
        if canonical is None:
            outcome.unknown_terms.append(
                UnknownTerm(field_path=field_path, original_value=raw)
            )
            outcome.flag_unknown_taxonomy = True
            continue

        outcome.canonical[field_path] = canonical
        if canonical != raw:
            outcome.normalizations.append(
                Normalization(
                    field_path=field_path,
                    original_value=raw,
                    canonical_value=canonical,
                )
            )
    return outcome
