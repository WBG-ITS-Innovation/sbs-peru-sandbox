# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the deterministic system_signal detector.

These tests exercise the four rules in
``sbs_api.agents.triage_signals.detect_system_signal`` directly. They
do not touch the database or any agent runtime — the detector is a
pure function over the canonical Annex 1-A inputs.

Locked rule semantics (May-2026 cockpit reshape):

* Outage keywords fire **only** when the product category is one of the
  digital-access channels.
* Fraud keywords fire on the narrative alone.
* Amount > 50,000 PEN fires **only** when the motivo is a fraud or
  unauthorised-operation code.
* Regulatory-breach indicator (set by the FI) fires unconditionally
  when present and ``True``.
* Reasons are reported as enum codes, never as raw narrative excerpts,
  so the PII-sentinel contract holds.
"""

from __future__ import annotations

import pytest

from sbs_api.agents.triage_signals import (
    AMOUNT_THRESHOLD_PEN,
    REASON_AMOUNT,
    REASON_FRAUD,
    REASON_OUTAGE,
    REASON_REGULATORY_BREACH,
    detect_system_signal,
)


# ---------------------------------------------------------------------------
# Negative cases
# ---------------------------------------------------------------------------


def test_clean_complaint_returns_no_signal():
    result = detect_system_signal(
        narrative="Cliente solicita devolución de comisión por mantenimiento.",
        product_category="TARJETA_CREDITO",
        motivo_code="COBRO_INDEBIDO",
        amount_claimed=120.50,
        regulatory_breach_indicator=False,
    )
    assert result.flag is False
    assert result.reasons == []


def test_empty_inputs_return_no_signal():
    result = detect_system_signal(
        narrative=None,
        product_category=None,
        motivo_code=None,
        amount_claimed=None,
        regulatory_breach_indicator=None,
    )
    assert result.flag is False
    assert result.reasons == []


def test_outage_keyword_without_gated_category_does_not_fire():
    """Outage language in an AFP context is not a system signal — the
    rule's category gate exists so 'no puedo acceder' to a pension
    portal does not promote every contact-form complaint to system."""
    result = detect_system_signal(
        narrative="No puedo acceder a mi reporte de aportes desde el martes.",
        product_category="AFP_PENSIONES",
        motivo_code="DEMORA_ATENCION",
    )
    assert result.flag is False


def test_amount_below_threshold_does_not_fire():
    result = detect_system_signal(
        narrative="Reclamo por monto.",
        product_category="TARJETA_CREDITO",
        motivo_code="OPERACION_NO_RECONOCIDA",
        amount_claimed=AMOUNT_THRESHOLD_PEN,  # equality is not greater-than
    )
    assert result.flag is False


def test_amount_above_threshold_but_wrong_motivo_does_not_fire():
    result = detect_system_signal(
        narrative="Reclamo por monto alto.",
        product_category="TARJETA_CREDITO",
        motivo_code="CALIDAD_SERVICIO",
        amount_claimed=AMOUNT_THRESHOLD_PEN + 1,
    )
    assert result.flag is False


# ---------------------------------------------------------------------------
# Positive cases — each rule in isolation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "narrative",
    [
        "El sistema está caído desde ayer y no puedo acceder.",
        "La plataforma caida no me deja ver el saldo.",
        "App no abre desde la mañana.",
        "Sistema no funciona, llevo 18 horas sin acceso.",
        "Sistema inaccesible y la transferencia no se procesó.",
    ],
)
def test_outage_keyword_with_gated_category_fires(narrative: str):
    result = detect_system_signal(
        narrative=narrative,
        product_category="TARJETA_CREDITO",
        motivo_code="DEMORA_ATENCION",
    )
    assert result.flag is True
    assert REASON_OUTAGE in result.reasons


@pytest.mark.parametrize(
    "narrative",
    [
        "Se trata de un fraude masivo en mi cuenta.",
        "Hubo hackeo a mi tarjeta.",
        "Existe suplantación de identidad en este caso.",
        "Es una estafa generalizada que afecta a varios clientes.",
        "Tengo múltiples cargos no autorizados.",
    ],
)
def test_fraud_keyword_fires_regardless_of_category(narrative: str):
    result = detect_system_signal(
        narrative=narrative,
        product_category="OTRO",  # no category gate for fraud
        motivo_code="OTRO",
    )
    assert result.flag is True
    assert REASON_FRAUD in result.reasons


def test_amount_above_threshold_with_fraud_motivo_fires():
    result = detect_system_signal(
        narrative="Operación no reconocida por monto elevado.",
        product_category="TARJETA_CREDITO",
        motivo_code="OPERACION_NO_RECONOCIDA",
        amount_claimed=50_001.0,
    )
    assert result.flag is True
    assert REASON_AMOUNT in result.reasons


def test_regulatory_breach_indicator_fires_alone():
    result = detect_system_signal(
        narrative="Reclamo administrativo sin lenguaje de outage ni fraude.",
        product_category="OTRO",
        motivo_code="OTRO",
        regulatory_breach_indicator=True,
    )
    assert result.flag is True
    assert result.reasons == [REASON_REGULATORY_BREACH]


# ---------------------------------------------------------------------------
# Combination + audit-shape invariants
# ---------------------------------------------------------------------------


def test_multiple_rules_emit_deduped_sorted_reasons():
    """The exact demo narrative — outage language plus the FI-set breach
    flag — must surface both reason codes, deduplicated and sorted."""
    result = detect_system_signal(
        narrative=(
            "sistema caído desde ayer, transferencia de S/. 8,500 no procesada, "
            "llevo 18 horas sin acceso"
        ),
        product_category="TARJETA_DEBITO",
        motivo_code="DEMORA_ATENCION",
        regulatory_breach_indicator=True,
    )
    assert result.flag is True
    assert result.reasons == sorted(set(result.reasons))
    assert REASON_OUTAGE in result.reasons
    assert REASON_REGULATORY_BREACH in result.reasons


def test_reasons_are_enum_codes_not_narrative_excerpts():
    """PII sentinel: ``system_signal_reasons`` must never replay the
    user's narrative back out. The codes are stable identifiers from
    the module's REASON_* constants."""
    narrative = "Sistema caído. DNI 12345678 transferencia 8500 no procesada."
    result = detect_system_signal(
        narrative=narrative,
        product_category="TARJETA_CREDITO",
        motivo_code="DEMORA_ATENCION",
    )
    for code in result.reasons:
        assert code.isupper()
        assert "_" in code or code.isalpha()
        # No substring of the narrative may leak into a reason code.
        for fragment in ("12345678", "8500", "caído", "transferencia"):
            assert fragment not in code
