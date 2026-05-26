"""Unit tests for the deterministic PII redaction engine (P11A / ADR 0044).

These tests use the canonical "Carlos Rodríguez Mendoza" PII bundle the
prompt specifies. Asserts:

* Every required entity type is detected.
* Replacements are stable per kind across runs.
* Amount mentions like ``S/ 700`` and ``700 soles`` are NOT redacted as
  account numbers.
* ``masked_preview`` produces a browser-safe BEFORE preview that
  still contains no raw PII.
* The engine is pure: the same input produces byte-identical output.
"""

from __future__ import annotations

import re

import pytest

from sbs_api.redaction import POLICY_VERSION, redact
from sbs_api.redaction.engine import masked_preview


# The golden PII bundle from the P11A brief.
GOLDEN_NARRATIVE = (
    "Carlos Rodríguez Mendoza reporta un cargo de S/ 700 en la cuenta "
    "0011-2233-4455-6677 vinculada a su tarjeta 4556 1234 5678 9999. "
    "DNI 12345678. Lo pueden contactar al +51 987 654 321 o al 987654321. "
    "Su correo es carlos.rodriguez@example.com."
)


def _kinds(entities) -> set[str]:
    return {e.kind for e in entities}


def test_all_required_entity_kinds_detected():
    result = redact(GOLDEN_NARRATIVE)
    kinds = _kinds(result.entities)
    # The required kinds per the P11A brief.
    assert "pii_name" in kinds
    assert "pii_id" in kinds
    assert "pii_phone" in kinds
    assert "pii_email" in kinds
    assert "pii_account" in kinds


def test_replacements_are_stable_and_numbered_per_kind():
    result = redact(GOLDEN_NARRATIVE)
    # Each kind gets its own counter starting at 1.
    replacements_by_kind: dict[str, list[str]] = {}
    for ent in result.entities:
        replacements_by_kind.setdefault(ent.kind, []).append(ent.replacement)

    for kind, reps in replacements_by_kind.items():
        prefix = {
            "pii_name": "<PERSON_",
            "pii_id": "<DNI_",
            "pii_phone": "<PHONE_",
            "pii_email": "<EMAIL_",
            "pii_account": "<ACCOUNT_",
        }[kind]
        for idx, rep in enumerate(reps, start=1):
            assert rep == f"{prefix}{idx}>", (kind, reps)


def test_redactor_does_not_redact_soles_amount_as_account():
    text = "El cargo fue de S/ 700 y otro pago en cuenta 0011-2233-4455-6677."
    result = redact(text)
    # The 0011-2233... account should still be detected.
    assert any(e.kind == "pii_account" for e in result.entities)
    # No account replacement should overlap with the S/ 700 region.
    for ent in result.entities:
        assert "700" not in ent.matched_value or ent.kind != "pii_account"
    # Redacted text still contains "S/ 700" literally.
    assert "S/ 700" in result.redacted_text


def test_redactor_handles_700_soles_suffix():
    text = "Un monto de 700 soles aparece en mi cuenta."
    result = redact(text)
    # No account/card detection on this short numeric span.
    assert not any(e.kind == "pii_account" for e in result.entities)
    assert "700 soles" in result.redacted_text


def test_known_demo_name_variants_detected():
    accented = "Carlos Rodríguez Mendoza llamó hoy."
    unaccented = "Carlos Rodriguez Mendoza llamó hoy."
    for text in (accented, unaccented):
        result = redact(text)
        kinds = _kinds(result.entities)
        assert "pii_name" in kinds, text


def test_pure_function_same_input_same_output():
    a = redact(GOLDEN_NARRATIVE)
    b = redact(GOLDEN_NARRATIVE)
    assert a.redacted_text == b.redacted_text
    assert a.policy_version == b.policy_version == POLICY_VERSION
    assert [e.replacement for e in a.entities] == [e.replacement for e in b.entities]


def test_redacted_text_contains_no_raw_pii():
    result = redact(GOLDEN_NARRATIVE)
    raw_strings = [
        "Carlos Rodríguez Mendoza",
        "Carlos Rodriguez Mendoza",
        "12345678",  # DNI
        "987 654 321",
        "987654321",
        "carlos.rodriguez@example.com",
        "4556 1234 5678 9999",
        "0011-2233-4455-6677",
    ]
    for needle in raw_strings:
        assert needle not in result.redacted_text, needle


def test_safe_entities_strip_matched_value():
    result = redact(GOLDEN_NARRATIVE)
    safe = result.safe_entities()
    assert safe
    for ent in safe:
        assert "matched_value" not in ent
        assert set(ent.keys()) == {"kind", "rule_id", "span", "replacement", "confidence"}


def test_schema_redactions_shape_matches_anonymizer_schema():
    result = redact(GOLDEN_NARRATIVE)
    items = result.schema_redactions()
    for item in items:
        assert set(item.keys()) == {"kind", "span"}
        assert item["kind"] in {
            "pii_name",
            "pii_id",
            "pii_account",
            "pii_phone",
            "pii_email",
            "pii_address",
        }
        assert isinstance(item["span"], list) and len(item["span"]) == 2


def test_masked_preview_keeps_partial_dni_phone_email_account():
    result = redact(GOLDEN_NARRATIVE)
    preview = masked_preview(GOLDEN_NARRATIVE, result.entities)
    # Browser-safe BEFORE should NOT contain full raw values.
    assert "Carlos Rodríguez Mendoza" not in preview
    assert "12345678" not in preview
    assert "carlos.rodriguez@example.com" not in preview
    assert "0011-2233-4455-6677" not in preview
    # But the partial-mask hints are present so the UI shows context.
    assert "<PERSON:masked>" in preview
    assert re.search(r"\*+5678", preview)  # last 4 digits of the DNI
    assert re.search(r"\*+@com", preview) or re.search(r"\*\*\*@", preview)


# ---------------------------------------------------------------------------
# P11 sandbox completion — RUC redaction (Peruvian taxpayer id, 11 digits)
# ---------------------------------------------------------------------------


def test_ruc_with_explicit_prefix_is_redacted():
    text = "El cliente reporta una operación contra la empresa RUC 20512345678 emisora."
    result = redact(text)
    kinds = _kinds(result.entities)
    assert "pii_ruc" in kinds, f"RUC not detected: {kinds}"
    assert "20512345678" not in result.redacted_text
    assert "<RUC_1>" in result.redacted_text


def test_bare_11_digit_run_is_redacted_as_ruc():
    text = "Sin prefijo: la contraparte 20512345678 figura en la queja."
    result = redact(text)
    assert "pii_ruc" in _kinds(result.entities)
    assert "20512345678" not in result.redacted_text


def test_ruc_does_not_swallow_dni_phone_or_account():
    text = (
        "DNI 12345678. RUC 20512345678. Llamar al +51 987 654 321. "
        "Tarjeta 4556 1234 5678 9999."
    )
    result = redact(text)
    kinds = _kinds(result.entities)
    for required in ("pii_id", "pii_ruc", "pii_phone", "pii_account"):
        assert required in kinds, (required, kinds)
    # No raw value should survive.
    for needle in ("12345678", "20512345678", "987 654 321", "4556 1234 5678 9999"):
        assert needle not in result.redacted_text, needle


def test_masked_preview_partials_ruc():
    text = "Empresa RUC 20512345678 emisora."
    result = redact(text)
    preview = masked_preview(text, result.entities)
    assert "20512345678" not in preview
    # last 4 digits preserved per the documented mask shape.
    assert "5678" in preview
