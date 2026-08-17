# SPDX-License-Identifier: Apache-2.0
"""Annex 1-A data-quality rules — DQ-A1A-007 through DQ-A1A-027.

P11 DQ completion. The existing six rules in
:mod:`sbs_api.data_quality.checks` continue to drive the aggregate
``data-quality-completed`` audit event with their original kebab-case
``rule_id``s; this module adds 21 additional rules with stable
``DQ-A1A-NNN`` ids covering the remaining Annex 1-A fields per
Res. SBS 04036-2022.

Per-rule output shape (each entry in ``RuleResult``):

* ``rule_id``        — stable identifier (e.g. ``DQ-A1A-007``).
* ``field_path``     — dot-path of the field that produced the result
                       (``narrative``, ``bancaseguros.producto``, ...).
* ``observed_value`` — PII-safe representation of what we saw. For
                       PII-bearing fields this is a token like
                       ``"absent"`` / ``"present"`` / ``"invalid-format"``;
                       for code-list violations it is the rejected
                       code (codes are not PII).
* ``expected``       — short human-readable describing what passed
                       would look like.
* ``severity``       — ``"error"`` / ``"warning"`` / ``"info"``.
* ``message``        — supervisor-readable Spanish sentence.

The orchestrator emits one ``dq-rule-violated`` audit row per result
in addition to the aggregated ``data-quality-completed`` event the
existing rules already produce.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable

from sbs_api.dq import load_codelist


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


Severity = str  # "error" / "warning" / "info"


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    field_path: str
    observed_value: str
    expected: str
    severity: Severity
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "field_path": self.field_path,
            "observed_value": self.observed_value,
            "expected": self.expected,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class Annex1AReport:
    results: list[RuleResult] = field(default_factory=list)

    def add(self, result: RuleResult | None) -> None:
        if result is not None:
            self.results.append(result)

    @property
    def errors(self) -> list[RuleResult]:
        return [r for r in self.results if r.severity == "error"]

    @property
    def warnings(self) -> list[RuleResult]:
        return [r for r in self.results if r.severity == "warning"]

    @property
    def infos(self) -> list[RuleResult]:
        return [r for r in self.results if r.severity == "info"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "results": [r.as_dict() for r in self.results],
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "info_count": len(self.infos),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _norm(value: Any) -> str | None:
    """Trim and return None for empty / whitespace-only strings."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_iso_date(value: str) -> date | None:
    """Parse an ISO 8601 date or date-time. Returns None on failure."""

    try:
        if "T" in value:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


# PII-bearing fields — observed_value must be a tag, not the raw value.
_PII_FIELDS = frozenset(
    {
        "numero_documento",
        "nombre_completo",
        "codigo_cliente",
        "narrative",
    }
)


def _safe_observed(field_path: str, raw: Any) -> str:
    if field_path in _PII_FIELDS:
        return "present" if _norm(raw) else "absent"
    text = _norm(raw)
    return text if text is not None else "absent"


# ---------------------------------------------------------------------------
# Field accessors — map both the Anexo 1-A acronyms and the
# user-friendly aliases the demo endpoint accepts.
# ---------------------------------------------------------------------------


def _get(payload: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        v = payload.get(k)
        if v is not None and str(v).strip() != "":
            return v
    return None


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


_DNI_RE = re.compile(r"^\d{8}$")
_RUC_RE = re.compile(r"^\d{11}$")
_CE_RE = re.compile(r"^[A-Z0-9]{8,12}$", re.IGNORECASE)
_UBIGEO_RE = re.compile(r"^\d{4}(\d{2})?$")  # 4 (dept+prov) or 6 (dept+prov+dist) digits
_AMOUNT_RE = re.compile(r"^\d+(\.\d{1,2})?$")


def _r_007_missing_tipo_documento(p: dict[str, Any]) -> RuleResult | None:
    v = _get(p, "tipo_documento", "tid_cli")
    if _norm(v):
        return None
    return RuleResult(
        rule_id="DQ-A1A-007",
        field_path="tipo_documento",
        observed_value="absent",
        expected="one of DNI / CE / RUC / PASAPORTE / PTP / OTRO",
        severity="error",
        message="Tipo de documento (Anexo 1-A campo 2) es obligatorio.",
    )


def _r_008_unknown_tipo_documento(p: dict[str, Any]) -> RuleResult | None:
    v = _norm(_get(p, "tipo_documento", "tid_cli"))
    if not v:
        return None
    cl = load_codelist("tipo_documento")
    if v.upper() in {c.upper() for c in cl.code_set}:
        return None
    return RuleResult(
        rule_id="DQ-A1A-008",
        field_path="tipo_documento",
        observed_value=v,
        expected=f"one of {sorted(cl.code_set)}",
        severity="warning",
        message=(
            f"Tipo de documento {v!r} no figura en el catálogo sandbox; "
            "revisar con SBS si el código es válido."
        ),
    )


def _r_009_numero_documento_format(p: dict[str, Any]) -> RuleResult | None:
    """Length / charset depends on the declared tipo_documento."""

    tipo = (_norm(_get(p, "tipo_documento", "tid_cli")) or "").upper()
    num_raw = _get(p, "numero_documento", "nro_cli")
    num = _norm(num_raw)
    if not num:
        # Presence is a separate rule (DQ-A1A-007 only covers tipo).
        return RuleResult(
            rule_id="DQ-A1A-009",
            field_path="numero_documento",
            observed_value="absent",
            expected="numeric / alphanumeric per tipo_documento",
            severity="error",
            message="Número de documento (Anexo 1-A campo 3) es obligatorio.",
        )
    # Strip whitespace / hyphens for the format check.
    canonical = re.sub(r"[\s\-]", "", num)
    ok = True
    expected = "alphanumeric"
    if tipo == "DNI":
        ok = bool(_DNI_RE.match(canonical))
        expected = "8 digits (DNI)"
    elif tipo == "RUC":
        ok = bool(_RUC_RE.match(canonical))
        expected = "11 digits (RUC)"
    elif tipo == "CE":
        ok = bool(_CE_RE.match(canonical))
        expected = "8-12 alphanumeric chars (CE)"
    elif tipo == "PASAPORTE":
        ok = bool(_CE_RE.match(canonical))
        expected = "alphanumeric (passport)"
    # Other tipo values pass through.
    if ok:
        return None
    return RuleResult(
        rule_id="DQ-A1A-009",
        field_path="numero_documento",
        # Never expose the raw document number — it is PII.
        observed_value="invalid-format",
        expected=expected,
        severity="error",
        message=(
            f"Número de documento no respeta el formato esperado para "
            f"tipo_documento={tipo or '<absent>'} ({expected})."
        ),
    )


def _r_010_missing_codigo_cliente(p: dict[str, Any]) -> RuleResult | None:
    v = _get(p, "codigo_cliente", "cod_cli")
    if _norm(v):
        return None
    return RuleResult(
        rule_id="DQ-A1A-010",
        field_path="codigo_cliente",
        observed_value="absent",
        expected="non-empty client id",
        severity="warning",
        message="Código de cliente (Anexo 1-A campo 5) no informado; recomendado para correlación.",
    )


def _r_011_invalid_fecha_ingreso(p: dict[str, Any]) -> RuleResult | None:
    v = _norm(_get(p, "fecha_ingreso", "received_at"))
    if v is None:
        return RuleResult(
            rule_id="DQ-A1A-011",
            field_path="fecha_ingreso",
            observed_value="absent",
            expected="ISO 8601 date or datetime",
            severity="error",
            message="Fecha de ingreso (Anexo 1-A campo 6) es obligatoria.",
        )
    if _parse_iso_date(v) is None:
        return RuleResult(
            rule_id="DQ-A1A-011",
            field_path="fecha_ingreso",
            observed_value="invalid-format",
            expected="ISO 8601 date or datetime",
            severity="error",
            message=f"Fecha de ingreso {v!r} no es ISO 8601.",
        )
    return None


def _r_012_missing_canal_ingreso(p: dict[str, Any]) -> RuleResult | None:
    v = _get(p, "canal_ingreso", "channel_in")
    if _norm(v):
        return None
    return RuleResult(
        rule_id="DQ-A1A-012",
        field_path="canal_ingreso",
        observed_value="absent",
        expected="Anexo A channel code",
        severity="error",
        message="Canal de ingreso (Anexo 1-A campo 7) es obligatorio.",
    )


def _r_013_unknown_canal_ingreso(p: dict[str, Any]) -> RuleResult | None:
    v = _norm(_get(p, "canal_ingreso", "channel_in"))
    if not v:
        return None
    cl = load_codelist("canales")
    if v in cl.code_set or v.upper() in {c.upper() for c in cl.code_set}:
        return None
    return RuleResult(
        rule_id="DQ-A1A-013",
        field_path="canal_ingreso",
        observed_value=v,
        expected="Anexo A channel code",
        severity="warning",
        message=f"Canal de ingreso {v!r} no figura en Anexo A.",
    )


def _r_014_unknown_canal_respuesta(p: dict[str, Any]) -> RuleResult | None:
    v = _norm(_get(p, "canal_respuesta"))
    if not v:
        return None
    cl = load_codelist("canal_reclamo")
    if v in cl.code_set or v.upper() in {c.upper() for c in cl.code_set}:
        return None
    return RuleResult(
        rule_id="DQ-A1A-014",
        field_path="canal_respuesta",
        observed_value=v,
        expected="Anexo A channel code",
        severity="warning",
        message=f"Canal de respuesta {v!r} no figura en Anexo A.",
    )


def _r_015_invalid_ubigeo(p: dict[str, Any]) -> RuleResult | None:
    v = _norm(_get(p, "ubigeo"))
    if not v:
        return None  # presence is optional per the Reglamento
    if _UBIGEO_RE.match(v):
        return None
    return RuleResult(
        rule_id="DQ-A1A-015",
        field_path="ubigeo",
        observed_value=v,
        expected="4-digit (dept+prov) or 6-digit (dept+prov+dist) INEI code",
        severity="warning",
        message=f"Ubigeo {v!r} no respeta el formato INEI (4 o 6 dígitos).",
    )


def _r_016_missing_submotivo(p: dict[str, Any]) -> RuleResult | None:
    v = _get(p, "submotivo", "submotive")
    if _norm(v):
        return None
    return RuleResult(
        rule_id="DQ-A1A-016",
        field_path="submotivo",
        observed_value="absent",
        expected="Anexo D sub-code (scoped to parent motivo)",
        severity="warning",
        message="Submotivo (Anexo 1-A campo 16) no informado.",
    )


def _r_017_invalid_monto_format(p: dict[str, Any]) -> RuleResult | None:
    v = _norm(_get(p, "monto_reclamado", "amount_claimed"))
    if v is None:
        return None
    if _AMOUNT_RE.match(v):
        return None
    return RuleResult(
        rule_id="DQ-A1A-017",
        field_path="monto_reclamado",
        observed_value=v,
        expected="numeric with up to 2 decimals (e.g. 450.00)",
        severity="warning",
        message=f"Monto reclamado {v!r} no respeta formato numérico.",
    )


def _r_018_unknown_moneda(p: dict[str, Any]) -> RuleResult | None:
    v = _norm(_get(p, "moneda"))
    if not v:
        return None  # currency is informational; spec is silent
    cl = load_codelist("moneda")
    if v.upper() in {c.upper() for c in cl.code_set}:
        return None
    return RuleResult(
        rule_id="DQ-A1A-018",
        field_path="moneda",
        observed_value=v,
        expected=f"ISO 4217 code; sandbox set: {sorted(cl.code_set)}",
        severity="warning",
        message=f"Código de moneda {v!r} no figura en el catálogo sandbox.",
    )


def _r_019_missing_estado(p: dict[str, Any]) -> RuleResult | None:
    v = _get(p, "estado", "status")
    if _norm(v):
        return None
    return RuleResult(
        rule_id="DQ-A1A-019",
        field_path="estado",
        observed_value="absent",
        expected="pendiente / atendido / anulado",
        severity="error",
        message="Estado del reclamo (Anexo 1-A campo 22) es obligatorio.",
    )


def _r_020_unknown_estado(p: dict[str, Any]) -> RuleResult | None:
    v = _norm(_get(p, "estado", "status"))
    if not v:
        return None
    cl = load_codelist("estado_reclamo")
    if v.lower() in {c.lower() for c in cl.code_set}:
        return None
    return RuleResult(
        rule_id="DQ-A1A-020",
        field_path="estado",
        observed_value=v,
        expected="pendiente / atendido / anulado",
        severity="error",
        message=f"Estado del reclamo {v!r} no es uno de pendiente/atendido/anulado.",
    )


def _r_021_atendido_without_fecha_resolucion(p: dict[str, Any]) -> RuleResult | None:
    estado = (_norm(_get(p, "estado", "status")) or "").lower()
    if estado != "atendido":
        return None
    if _norm(_get(p, "fecha_resolucion")):
        return None
    return RuleResult(
        rule_id="DQ-A1A-021",
        field_path="fecha_resolucion",
        observed_value="absent",
        expected="ISO 8601 date — required when estado=atendido",
        severity="error",
        message="estado=atendido exige fecha_resolucion (Anexo 1-A campo 11).",
    )


def _r_022_atendido_without_resolucion(p: dict[str, Any]) -> RuleResult | None:
    estado = (_norm(_get(p, "estado", "status")) or "").lower()
    if estado != "atendido":
        return None
    res = (_norm(_get(p, "resolucion_reclamo")) or "").lower()
    if res in {"favor_usuario", "favor_empresa"}:
        return None
    return RuleResult(
        rule_id="DQ-A1A-022",
        field_path="resolucion_reclamo",
        observed_value=res or "absent",
        expected="favor_usuario / favor_empresa — required when estado=atendido",
        severity="error",
        message="estado=atendido exige resolucion_reclamo (Anexo 1-A campo 18).",
    )


def _r_023_fecha_resolucion_before_ingreso(p: dict[str, Any]) -> RuleResult | None:
    fi = _norm(_get(p, "fecha_ingreso", "received_at"))
    fr = _norm(_get(p, "fecha_resolucion"))
    if not fi or not fr:
        return None
    d_ingreso = _parse_iso_date(fi)
    d_resolucion = _parse_iso_date(fr)
    if d_ingreso is None or d_resolucion is None:
        # Format errors are surfaced by their own rules; don't double-report.
        return None
    if d_resolucion >= d_ingreso:
        return None
    return RuleResult(
        rule_id="DQ-A1A-023",
        field_path="fecha_resolucion",
        observed_value=fr,
        expected=f">= fecha_ingreso ({fi})",
        severity="error",
        message=(
            f"fecha_resolucion {fr} es anterior a fecha_ingreso {fi}; "
            "violación temporal."
        ),
    )


def _r_024_bancaseguros_without_producto(p: dict[str, Any]) -> RuleResult | None:
    flag = (_norm(_get(p, "bancaseguros")) or "").lower()
    if flag != "si":
        return None
    if _norm(_get(p, "producto_bancaseguros")):
        return None
    return RuleResult(
        rule_id="DQ-A1A-024",
        field_path="producto_bancaseguros",
        observed_value="absent",
        expected="Anexo B seguros code — required when bancaseguros=si",
        severity="error",
        message="bancaseguros=si exige producto_bancaseguros (Anexo 1-A campo 25).",
    )


def _r_025_bancaseguros_without_motivo(p: dict[str, Any]) -> RuleResult | None:
    flag = (_norm(_get(p, "bancaseguros")) or "").lower()
    if flag != "si":
        return None
    if _norm(_get(p, "motivo_bancaseguros")):
        return None
    return RuleResult(
        rule_id="DQ-A1A-025",
        field_path="motivo_bancaseguros",
        observed_value="absent",
        expected="Anexo C seguros code — required when bancaseguros=si",
        severity="error",
        message="bancaseguros=si exige motivo_bancaseguros (Anexo 1-A campo 26).",
    )


def _r_026_bancaseguros_without_submotivo(p: dict[str, Any]) -> RuleResult | None:
    flag = (_norm(_get(p, "bancaseguros")) or "").lower()
    if flag != "si":
        return None
    if _norm(_get(p, "submotivo_bancaseguros")):
        return None
    return RuleResult(
        rule_id="DQ-A1A-026",
        field_path="submotivo_bancaseguros",
        observed_value="absent",
        expected="Anexo D seguros sub-code — recommended when bancaseguros=si",
        severity="warning",
        message="bancaseguros=si recomienda submotivo_bancaseguros (Anexo 1-A campo 27).",
    )


def _r_027_institution_not_in_registry(
    p: dict[str, Any], *, known_institutions: frozenset[str] | None = None
) -> RuleResult | None:
    if known_institutions is None:
        return None
    iid = _norm(_get(p, "institution_id"))
    if iid is None or iid in known_institutions:
        return None
    return RuleResult(
        rule_id="DQ-A1A-027",
        field_path="institution_id",
        observed_value=iid,
        expected=f"institution_id in known registry ({sorted(known_institutions)})",
        severity="warning",
        message=f"institution_id {iid!r} no figura en el registro de instituciones onboarded.",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


# Ordered registry — used by both the runner and the tests / docs to
# enumerate the 21 rules in id-order.
_RULE_REGISTRY: tuple[tuple[str, Callable[..., RuleResult | None]], ...] = (
    ("DQ-A1A-007", _r_007_missing_tipo_documento),
    ("DQ-A1A-008", _r_008_unknown_tipo_documento),
    ("DQ-A1A-009", _r_009_numero_documento_format),
    ("DQ-A1A-010", _r_010_missing_codigo_cliente),
    ("DQ-A1A-011", _r_011_invalid_fecha_ingreso),
    ("DQ-A1A-012", _r_012_missing_canal_ingreso),
    ("DQ-A1A-013", _r_013_unknown_canal_ingreso),
    ("DQ-A1A-014", _r_014_unknown_canal_respuesta),
    ("DQ-A1A-015", _r_015_invalid_ubigeo),
    ("DQ-A1A-016", _r_016_missing_submotivo),
    ("DQ-A1A-017", _r_017_invalid_monto_format),
    ("DQ-A1A-018", _r_018_unknown_moneda),
    ("DQ-A1A-019", _r_019_missing_estado),
    ("DQ-A1A-020", _r_020_unknown_estado),
    ("DQ-A1A-021", _r_021_atendido_without_fecha_resolucion),
    ("DQ-A1A-022", _r_022_atendido_without_resolucion),
    ("DQ-A1A-023", _r_023_fecha_resolucion_before_ingreso),
    ("DQ-A1A-024", _r_024_bancaseguros_without_producto),
    ("DQ-A1A-025", _r_025_bancaseguros_without_motivo),
    ("DQ-A1A-026", _r_026_bancaseguros_without_submotivo),
    ("DQ-A1A-027", _r_027_institution_not_in_registry),
)


RULE_IDS: tuple[str, ...] = tuple(rid for rid, _ in _RULE_REGISTRY)

POLICY_VERSION = "annex-1a-v1"


def run_annex_1a_checks(
    payload: dict[str, Any],
    *,
    known_institutions: frozenset[str] | None = None,
) -> Annex1AReport:
    """Run the 21 Annex 1-A DQ rules against ``payload``.

    ``payload`` is the institution-submitted request dict (already
    redacted by the time the orchestrator calls this — the rules in
    this module never touch the raw narrative). ``known_institutions``
    is an optional registry of onboarded ids for rule
    ``DQ-A1A-027`` (reference comparison); if absent, rule 027 is a
    no-op.
    """

    report = Annex1AReport()
    for rule_id, fn in _RULE_REGISTRY:
        try:
            if rule_id == "DQ-A1A-027":
                report.add(fn(payload, known_institutions=known_institutions))
            else:
                report.add(fn(payload))
        except Exception as exc:  # noqa: BLE001
            # A rule that crashes is itself a data-quality concern,
            # but it must not break the request. Surface it as a
            # warning so the supervisor sees it and the request still
            # produces an accepted/accepted_with_warnings receipt.
            report.add(
                RuleResult(
                    rule_id=rule_id,
                    field_path="<engine>",
                    observed_value=f"exception: {type(exc).__name__}",
                    expected="rule should not raise",
                    severity="warning",
                    message=f"DQ rule {rule_id} crashed: {exc}",
                )
            )
    return report
