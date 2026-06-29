# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the Annex 1-A DQ rules (DQ-A1A-007 through DQ-A1A-027).

One happy path + one (or more) failure path per rule. The valid
baseline below is a payload that should pass *every* rule when no
modifications are applied; each test mutates a copy to provoke its
target rule.

These tests run in-process against ``run_annex_1a_checks`` and do
not require Postgres. The orchestrator-level integration is exercised
separately by the test_sandbox_granular_api / test_live_ingestion
suites.
"""

from __future__ import annotations

import pytest

from sbs_api.data_quality.annex_1a_rules import (
    RULE_IDS,
    run_annex_1a_checks,
)


# ---------------------------------------------------------------------------
# Baseline payload — Annex-1A-complete; every rule passes.
# ---------------------------------------------------------------------------


KNOWN_IIDS = frozenset({"SBS-001234", "SBS-005678", "SBS-009012"})


VALID_BASE: dict = {
    "institution_id": "SBS-001234",
    "institution_complaint_id": "BCO-2026-0001",
    # Field 2 + 3
    "tipo_documento": "DNI",
    "numero_documento": "47291834",
    # Field 5
    "codigo_cliente": "CLI-0001",
    # Field 6
    "fecha_ingreso": "2026-05-26",
    # Field 7 + 12 — numeric Anexo A codes
    "canal_ingreso": "10",
    "canal_respuesta": "10",
    # Field 8 — channel_operation handled by legacy rules
    "channel_operation": "APP_MOVIL",
    # Field 13
    "ubigeo": "150101",
    # Field 14 + 15 — handled by legacy rules
    "product": "TARJETA_CREDITO",
    "motive": "COBRO_INDEBIDO",
    # Field 16
    "submotive": "30",
    # Field 17 — narrative is on the request model but checked by the
    # narrative-too-short rule in the legacy engine, not here.
    "narrative": "Detalle del reclamo del cliente con suficiente extensión textual.",
    # Field 18
    "resolucion_reclamo": "favor_usuario",
    # Field 20 + currency
    "amount_claimed": "450.00",
    "moneda": "PEN",
    # Field 22
    "status": "atendido",
    # Field 11 — required because estado=atendido
    "fecha_resolucion": "2026-05-26",
    # Field 24 + bancaseguros block (trigger=no → 25/26/27 optional)
    "bancaseguros": "no",
}


def _run(payload: dict) -> list:
    return run_annex_1a_checks(payload, known_institutions=KNOWN_IIDS).results


def _ids(results) -> set[str]:
    return {r.rule_id for r in results}


# ---------------------------------------------------------------------------
# Baseline + registry sanity
# ---------------------------------------------------------------------------


def test_rule_registry_has_exactly_21_rules():
    assert len(RULE_IDS) == 21
    assert RULE_IDS[0] == "DQ-A1A-007"
    assert RULE_IDS[-1] == "DQ-A1A-027"


def test_baseline_payload_fires_no_rules():
    results = _run(VALID_BASE)
    assert results == [], [
        f"{r.rule_id}: {r.message}" for r in results
    ]


# ---------------------------------------------------------------------------
# DQ-A1A-007 — missing tipo_documento
# ---------------------------------------------------------------------------


def test_007_happy():
    assert "DQ-A1A-007" not in _ids(_run(VALID_BASE))


def test_007_fail_when_missing():
    p = {**VALID_BASE}
    del p["tipo_documento"]
    fired = _ids(_run(p))
    assert "DQ-A1A-007" in fired


# ---------------------------------------------------------------------------
# DQ-A1A-008 — unknown tipo_documento code
# ---------------------------------------------------------------------------


def test_008_happy():
    assert "DQ-A1A-008" not in _ids(_run(VALID_BASE))


def test_008_fail_on_unknown_tipo():
    p = {**VALID_BASE, "tipo_documento": "INVENTADO"}
    assert "DQ-A1A-008" in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-009 — numero_documento format (DNI=8 / RUC=11 / CE=alphanum)
# ---------------------------------------------------------------------------


def test_009_happy_dni():
    assert "DQ-A1A-009" not in _ids(_run(VALID_BASE))


def test_009_happy_ruc():
    p = {**VALID_BASE, "tipo_documento": "RUC", "numero_documento": "20512345678"}
    assert "DQ-A1A-009" not in _ids(_run(p))


def test_009_fail_dni_wrong_length():
    p = {**VALID_BASE, "numero_documento": "12345"}
    assert "DQ-A1A-009" in _ids(_run(p))


def test_009_fail_ruc_wrong_length():
    p = {**VALID_BASE, "tipo_documento": "RUC", "numero_documento": "20512345"}
    assert "DQ-A1A-009" in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-010 — missing codigo_cliente (warning)
# ---------------------------------------------------------------------------


def test_010_happy():
    assert "DQ-A1A-010" not in _ids(_run(VALID_BASE))


def test_010_warns_when_missing():
    p = {**VALID_BASE}
    del p["codigo_cliente"]
    fired = _ids(_run(p))
    assert "DQ-A1A-010" in fired


# ---------------------------------------------------------------------------
# DQ-A1A-011 — invalid fecha_ingreso (ISO 8601)
# ---------------------------------------------------------------------------


def test_011_happy():
    assert "DQ-A1A-011" not in _ids(_run(VALID_BASE))


def test_011_fail_on_garbage():
    p = {**VALID_BASE, "fecha_ingreso": "26-05-2026"}  # not ISO
    assert "DQ-A1A-011" in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-012 — missing canal_ingreso
# ---------------------------------------------------------------------------


def test_012_happy():
    assert "DQ-A1A-012" not in _ids(_run(VALID_BASE))


def test_012_fail_on_absence():
    p = {**VALID_BASE}
    del p["canal_ingreso"]
    assert "DQ-A1A-012" in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-013 — unknown canal_ingreso code (warning)
# ---------------------------------------------------------------------------


def test_013_happy():
    assert "DQ-A1A-013" not in _ids(_run(VALID_BASE))


def test_013_warns_on_unknown_code():
    p = {**VALID_BASE, "canal_ingreso": "ZZZZ"}
    assert "DQ-A1A-013" in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-014 — unknown canal_respuesta code (warning)
# ---------------------------------------------------------------------------


def test_014_happy():
    assert "DQ-A1A-014" not in _ids(_run(VALID_BASE))


def test_014_warns_on_unknown_code():
    p = {**VALID_BASE, "canal_respuesta": "QQ"}
    assert "DQ-A1A-014" in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-015 — invalid ubigeo format
# ---------------------------------------------------------------------------


def test_015_happy_6_digit():
    assert "DQ-A1A-015" not in _ids(_run(VALID_BASE))


def test_015_happy_4_digit():
    p = {**VALID_BASE, "ubigeo": "1501"}
    assert "DQ-A1A-015" not in _ids(_run(p))


def test_015_fail_on_letters():
    p = {**VALID_BASE, "ubigeo": "ABCDEF"}
    assert "DQ-A1A-015" in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-016 — missing submotivo
# ---------------------------------------------------------------------------


def test_016_happy():
    assert "DQ-A1A-016" not in _ids(_run(VALID_BASE))


def test_016_warns_when_missing():
    p = {**VALID_BASE}
    del p["submotive"]
    assert "DQ-A1A-016" in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-017 — invalid monto_reclamado format
# ---------------------------------------------------------------------------


def test_017_happy():
    assert "DQ-A1A-017" not in _ids(_run(VALID_BASE))


def test_017_fail_on_string_amount():
    p = {**VALID_BASE, "amount_claimed": "S/450.00"}
    assert "DQ-A1A-017" in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-018 — unknown moneda code
# ---------------------------------------------------------------------------


def test_018_happy():
    assert "DQ-A1A-018" not in _ids(_run(VALID_BASE))


def test_018_warns_on_unknown_currency():
    p = {**VALID_BASE, "moneda": "ZZZ"}
    assert "DQ-A1A-018" in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-019 — missing estado
# ---------------------------------------------------------------------------


def test_019_happy():
    assert "DQ-A1A-019" not in _ids(_run(VALID_BASE))


def test_019_fail_on_absence():
    p = {**VALID_BASE}
    del p["status"]
    assert "DQ-A1A-019" in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-020 — unknown estado code
# ---------------------------------------------------------------------------


def test_020_happy():
    assert "DQ-A1A-020" not in _ids(_run(VALID_BASE))


def test_020_fail_on_invalid_estado():
    p = {**VALID_BASE, "status": "inventado"}
    fired = _ids(_run(p))
    assert "DQ-A1A-020" in fired


# ---------------------------------------------------------------------------
# DQ-A1A-021 — atendido without fecha_resolucion
# ---------------------------------------------------------------------------


def test_021_happy_pendiente_no_resolucion():
    p = {**VALID_BASE, "status": "pendiente"}
    del p["fecha_resolucion"]
    assert "DQ-A1A-021" not in _ids(_run(p))


def test_021_fail_atendido_without_fecha():
    p = {**VALID_BASE}
    del p["fecha_resolucion"]
    assert "DQ-A1A-021" in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-022 — atendido without resolucion_reclamo
# ---------------------------------------------------------------------------


def test_022_happy():
    assert "DQ-A1A-022" not in _ids(_run(VALID_BASE))


def test_022_fail_atendido_without_resolucion():
    p = {**VALID_BASE}
    del p["resolucion_reclamo"]
    assert "DQ-A1A-022" in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-023 — fecha_resolucion before fecha_ingreso
# ---------------------------------------------------------------------------


def test_023_happy():
    assert "DQ-A1A-023" not in _ids(_run(VALID_BASE))


def test_023_fail_inverted_dates():
    p = {**VALID_BASE, "fecha_resolucion": "2026-05-25"}  # before ingreso 26
    assert "DQ-A1A-023" in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-024 — bancaseguros trigger without producto_bancaseguros
# ---------------------------------------------------------------------------


def test_024_happy_no_trigger():
    assert "DQ-A1A-024" not in _ids(_run(VALID_BASE))


def test_024_fail_trigger_without_producto():
    p = {**VALID_BASE, "bancaseguros": "si"}  # producto_bancaseguros missing
    assert "DQ-A1A-024" in _ids(_run(p))


def test_024_happy_trigger_with_producto():
    p = {
        **VALID_BASE,
        "bancaseguros": "si",
        "producto_bancaseguros": "103",
        "motivo_bancaseguros": "44",
        "submotivo_bancaseguros": "50",
    }
    assert "DQ-A1A-024" not in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-025 — bancaseguros trigger without motivo_bancaseguros
# ---------------------------------------------------------------------------


def test_025_happy():
    assert "DQ-A1A-025" not in _ids(_run(VALID_BASE))


def test_025_fail_trigger_without_motivo():
    p = {**VALID_BASE, "bancaseguros": "si", "producto_bancaseguros": "103"}
    assert "DQ-A1A-025" in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-026 — bancaseguros trigger without submotivo (warning)
# ---------------------------------------------------------------------------


def test_026_happy():
    assert "DQ-A1A-026" not in _ids(_run(VALID_BASE))


def test_026_warns_trigger_without_submotivo():
    p = {
        **VALID_BASE,
        "bancaseguros": "si",
        "producto_bancaseguros": "103",
        "motivo_bancaseguros": "44",
        # no submotivo_bancaseguros
    }
    assert "DQ-A1A-026" in _ids(_run(p))


# ---------------------------------------------------------------------------
# DQ-A1A-027 — institution_id reference check (warning)
# ---------------------------------------------------------------------------


def test_027_happy():
    assert "DQ-A1A-027" not in _ids(_run(VALID_BASE))


def test_027_warns_on_unknown_institution():
    p = {**VALID_BASE, "institution_id": "SBS-999999"}
    assert "DQ-A1A-027" in _ids(_run(p))


def test_027_noop_when_registry_absent():
    """If the orchestrator is unable to load the FI registry, rule 027
    silently no-ops rather than failing the request."""

    from sbs_api.data_quality.annex_1a_rules import run_annex_1a_checks

    report = run_annex_1a_checks(
        {**VALID_BASE, "institution_id": "SBS-999999"},
        known_institutions=None,
    )
    assert "DQ-A1A-027" not in {r.rule_id for r in report.results}


# ---------------------------------------------------------------------------
# PII safety on observed_value — never leak the raw value of a PII field
# ---------------------------------------------------------------------------


def test_numero_documento_failure_does_not_expose_raw_value():
    p = {**VALID_BASE, "numero_documento": "47291834-leak-suffix"}
    results = _run(p)
    rule_009 = next(r for r in results if r.rule_id == "DQ-A1A-009")
    assert "47291834" not in rule_009.observed_value
    assert "leak" not in rule_009.observed_value
    assert rule_009.observed_value == "invalid-format"


# ---------------------------------------------------------------------------
# Aggregate severity rollup
# ---------------------------------------------------------------------------


def test_all_severities_propagate_to_report():
    p = {**VALID_BASE}
    # Trigger an error + a warning + an info-only path is not implemented;
    # ensure errors and warnings are correctly counted.
    p["tipo_documento"] = "INVENTADO"  # warning DQ-A1A-008
    del p["status"]  # error DQ-A1A-019
    report = run_annex_1a_checks(p, known_institutions=KNOWN_IIDS)
    assert any(r.rule_id == "DQ-A1A-008" for r in report.warnings)
    assert any(r.rule_id == "DQ-A1A-019" for r in report.errors)
