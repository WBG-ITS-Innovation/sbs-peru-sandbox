# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the deterministic data-quality checker (P11A / ADR 0045).

The DQ checker runs on a **redacted** narrative — it never sees raw
PII. Tests cover:

* Structural errors for missing institution_complaint_id, narrative,
  product, motive.
* Warning for missing channel_operation.
* Wallet-clue heuristic suggests APP_MOVIL when the narrative mentions
  Yape / Plin / billetera and channel_operation is blank or generic.
* Amount-extraction heuristic suggests an amount_claimed value when
  the narrative mentions ``S/ 700`` / ``700 soles`` / ``monto 700``
  but the structured field is empty.
* Narrative-too-short surfaces a warning.
* Unknown product / motive / channel_operation codes surface warnings
  but not errors.
* policy_version is the documented ``dq-demo-v1``.
"""

from __future__ import annotations

from sbs_api.data_quality import POLICY_VERSION, run_checks


def _ids(items, key="rule_id"):
    return {it[key] for it in items}


def test_all_required_fields_missing_records_four_errors():
    report = run_checks(fields={}, redacted_narrative="")
    assert {"missing-institution-complaint-id", "missing-narrative", "missing-product", "missing-motive"} <= _ids(report.errors)
    assert report.has_blocking_errors is True
    assert report.policy_version == POLICY_VERSION


def test_missing_channel_operation_warns_but_does_not_error():
    fields = {
        "institution_complaint_id": "X-1",
        "product": "TARJETA_CREDITO",
        "motive": "COBRO_INDEBIDO",
    }
    report = run_checks(
        fields=fields,
        redacted_narrative=(
            "Cliente reporta un cargo no reconocido en su tarjeta de crédito. "
            "Solicita reversa y revisión completa."
        ),
    )
    assert "missing-channel-operation" in _ids(report.warnings)
    assert report.has_blocking_errors is False


def test_wallet_clue_with_blank_channel_operation_suggests_app_movil():
    report = run_checks(
        fields={
            "institution_complaint_id": "X-1",
            "product": "TARJETA_CREDITO",
            "motive": "COBRO_INDEBIDO",
        },
        redacted_narrative=(
            "Recibí notificaciones por mi billetera digital y desde Yape no puedo "
            "transferir nada al beneficiario."
        ),
    )
    suggested = [s for s in report.suggested_enrichments if s["field"] == "channel_operation"]
    assert suggested
    assert suggested[0]["suggested_value"] == "APP_MOVIL"
    assert "wallet-clue-without-mobile-channel" in _ids(report.warnings)


def test_amount_extraction_suggests_value_when_amount_claimed_missing():
    report = run_checks(
        fields={
            "institution_complaint_id": "X-1",
            "product": "TARJETA_CREDITO",
            "motive": "COBRO_INDEBIDO",
            "channel_operation": "APP_MOVIL",
        },
        redacted_narrative=(
            "El cargo fue de S/ 700 y el cliente solicita reversa inmediata "
            "del importe completo."
        ),
    )
    suggested = [s for s in report.suggested_enrichments if s["field"] == "amount_claimed"]
    assert suggested
    assert suggested[0]["suggested_value"] == "700"
    assert report.extracted_fields.get("amount_claimed_extracted") == "700"


def test_amount_extraction_handles_soles_suffix():
    report = run_checks(
        fields={
            "institution_complaint_id": "X-1",
            "product": "TARJETA_CREDITO",
            "motive": "COBRO_INDEBIDO",
            "channel_operation": "APP_MOVIL",
        },
        redacted_narrative="El monto reclamado es de 1250.50 soles aproximadamente.",
    )
    suggested = [s for s in report.suggested_enrichments if s["field"] == "amount_claimed"]
    assert suggested
    assert suggested[0]["suggested_value"] == "1250.50"


def test_amount_not_suggested_when_field_already_filled():
    report = run_checks(
        fields={
            "institution_complaint_id": "X-1",
            "product": "TARJETA_CREDITO",
            "motive": "COBRO_INDEBIDO",
            "channel_operation": "APP_MOVIL",
            "amount_claimed": "700",
        },
        redacted_narrative="El cargo fue de S/ 700 y solicito reversa inmediata por favor.",
    )
    suggested = [s for s in report.suggested_enrichments if s["field"] == "amount_claimed"]
    assert suggested == []


def test_short_narrative_emits_warning():
    report = run_checks(
        fields={
            "institution_complaint_id": "X-1",
            "product": "TARJETA_CREDITO",
            "motive": "COBRO_INDEBIDO",
            "channel_operation": "APP_MOVIL",
        },
        redacted_narrative="Cargo no reconocido.",
    )
    assert "narrative-too-short" in _ids(report.warnings)


def test_unknown_product_code_warns_does_not_error():
    report = run_checks(
        fields={
            "institution_complaint_id": "X-1",
            "product": "ROCKETSHIP",
            "motive": "COBRO_INDEBIDO",
            "channel_operation": "APP_MOVIL",
        },
        redacted_narrative=(
            "Cliente reporta cargo no reconocido en una operación reciente "
            "que solicita revisar."
        ),
    )
    assert "unknown-product-code" in _ids(report.warnings)
    assert "missing-product" not in _ids(report.errors)


def test_as_dict_round_trips_policy_version():
    report = run_checks(fields={}, redacted_narrative="")
    payload = report.as_dict()
    assert payload["policy_version"] == POLICY_VERSION
    assert set(payload.keys()) == {
        "errors",
        "warnings",
        "suggested_enrichments",
        "extracted_fields",
        "policy_version",
    }
