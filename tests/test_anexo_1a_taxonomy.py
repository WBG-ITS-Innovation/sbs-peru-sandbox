"""Anexo 1-A taxonomy tests.

Each test asserts a constraint of the 15-field subset documented in ADR 0026
and reconciled against Anexo N° 1-A of Resolución SBS N° 04036-2022. The
docstring on each test names the resolución section (or marks the constraint
as a prototype divergence with no resolución counterpart, per ADR 0026).
"""

from __future__ import annotations

import pytest

from sbs_api.models import (
    Channel,
    Complaint,
    ComplainantAgeRange,
    ComplainantDocType,
    DescriptionLanguage,
    MotivoCode,
    ProductCategory,
    ResolutionStatus,
    Severity,
    SubmissionMethod,
)


def test_complaint_id_format_is_institution_year_sequence():
    """Resolución Anexo 1-A #1 — Código del reclamo is described as a
    correlative used by the empresa for registration. The 15-field subset
    formalises this as `<prefix>-<year>-<sequence>` for sandbox demonstration
    purposes; the resolución does not mandate a specific format, only that
    the value uniquely identifies the reclamo within the empresa. ADR 0026
    documents this as a prototype-level refinement."""
    valid = ["BCO-2026-000017", "F-2026-1234567", "CO-2025-0000010001"]
    for v in valid:
        Complaint.model_validate(
            _kwargs(complaint_id=v) | {"complaint_id": v},
        )


def test_received_date_is_iso_8601():
    """Resolución Anexo 1-A #6 — Fecha de ingreso. ISO 8601 (YYYY-MM-DD)."""
    c = Complaint(**_kwargs())
    assert c.received_date.isoformat() == "2026-05-12"


def test_complainant_doc_type_subset_codes():
    """Resolución Anexo 1-A #2 — Tipo de documento de identidad (Anexo A
    subset). The May 25 sandbox subset is DNI, CE, PASAPORTE, RUC, OTRO."""
    expected = {"DNI", "CE", "PASAPORTE", "RUC", "OTRO"}
    actual = {member.value for member in ComplainantDocType}
    assert actual == expected


def test_product_category_subset_codes():
    """Resolución Anexo 1-A #14 — Operación/Servicio/Producto (Anexo B subset).
    Full Anexo B code list is deferred to Part 11 (Standards Pack distribution)."""
    expected = {
        "DEPOSITOS",
        "CREDITOS",
        "TARJETA_CREDITO",
        "TARJETA_DEBITO",
        "SEGUROS",
        "AFP_PENSIONES",
        "COOPAC",
        "OTRO",
    }
    actual = {member.value for member in ProductCategory}
    assert actual == expected


def test_channel_subset_codes():
    """Resolución Anexo 1-A #7 — Canal de ingreso (Anexo A subset). Full
    Anexo A code list is deferred to Part 11."""
    expected = {
        "AGENCIA",
        "WEB",
        "APP_MOVIL",
        "TELEFONO",
        "CORREO",
        "PRESENCIAL_SBS",
        "OTRO",
    }
    actual = {member.value for member in Channel}
    assert actual == expected


def test_submission_method_subset_codes():
    """Resolución Anexo 1-A #8 — Canal de operación (Anexo A operation-channel
    subset). Distinct from Channel (#7 canal de ingreso)."""
    expected = {
        "AGENCIA",
        "CAJERO",
        "APP_MOVIL",
        "WEB",
        "POS",
        "AGENTE_CORRESPONSAL",
        "OTRO",
    }
    actual = {member.value for member in SubmissionMethod}
    assert actual == expected


def test_motivo_codes_subset():
    """Resolución Anexo 1-A #15 — Motivo del reclamo SBS (Anexo C subset)."""
    expected = {
        "COBRO_INDEBIDO",
        "OPERACION_NO_RECONOCIDA",
        "DEMORA_ATENCION",
        "INFORMACION_INCORRECTA",
        "INCUMPLIMIENTO_CONTRATO",
        "CALIDAD_SERVICIO",
        "PUBLICIDAD_ENGANOSA",
        "OTRO",
    }
    actual = {member.value for member in MotivoCode}
    assert actual == expected


def test_resolution_status_exact_resolucion_wording():
    """Resolución Anexo 1-A #22 — Estado. The resolución explicitly enumerates
    the values: pendiente, atendido, anulado (lowercase Spanish)."""
    assert ResolutionStatus.PENDIENTE.value == "pendiente"
    assert ResolutionStatus.ATENDIDO.value == "atendido"
    assert ResolutionStatus.ANULADO.value == "anulado"
    assert {m.value for m in ResolutionStatus} == {"pendiente", "atendido", "anulado"}


def test_complainant_district_is_inei_ubigeo_dept_prov():
    """Resolución Anexo 1-A #13 — Ubicación geográfica. INEI ubigeo at
    department + province precision is a 4-digit code (e.g., 1501 = Lima/Lima).
    The resolución also documents '9999' for complaints submitted from abroad."""
    Complaint(**_kwargs(complainant_district="1501"))
    Complaint(**_kwargs(complainant_district="9999"))


def test_complainant_age_range_no_resolucion_counterpart():
    """Prototype divergence — no Anexo 1-A counterpart. Used in lieu of
    Anexo 1-A's PII-bearing fields (DNI, full name). ADR 0026."""
    expected = {
        "UNDER_25",
        "25_34",
        "35_44",
        "45_54",
        "55_64",
        "OVER_64",
        "UNKNOWN",
    }
    actual = {member.value for member in ComplainantAgeRange}
    assert actual == expected


def test_severity_no_resolucion_counterpart():
    """Prototype divergence — no Anexo 1-A counterpart. Used by Part 5+
    supervisory agents for triage. ADR 0026."""
    assert {m.value for m in Severity} == {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def test_description_language_no_resolucion_counterpart():
    """Prototype divergence — no Anexo 1-A counterpart. Included to handle
    Quechua / Aymara / English narratives. ADR 0026."""
    assert {m.value for m in DescriptionLanguage} == {"es", "qu", "ay", "en"}


def test_description_text_length_bounds():
    """Resolución Anexo 1-A #17 — Detalle completo de reclamo. The resolución
    does not specify a hard max length; the 8000-character upper bound is a
    sandbox guardrail (ADR 0026). The 10-character lower bound is to reject
    empty / whitespace-only submissions."""
    short = "x" * 9
    long_ok = "x" * 8000
    too_long = "x" * 8001
    with pytest.raises(Exception):
        Complaint(**_kwargs(description_text=short))
    Complaint(**_kwargs(description_text=long_ok))
    with pytest.raises(Exception):
        Complaint(**_kwargs(description_text=too_long))


def test_pii_bearing_anexo_fields_are_absent():
    """The resolución's PII-bearing fields (Anexo 1-A #3 Número de documento,
    #4 Nombre completo del cliente, #5 Código de cliente) are deliberately
    excluded from the May 25 sandbox subset. The sandbox uses pseudonymous
    identifiers (complaint_id, institution_id) instead. ADR 0026.

    This test asserts the model does *not* accept those resolución field
    names — they should be rejected as unknown fields."""
    extra_pii = {
        "numero_documento": "12345678",
        "nombre_completo": "Juan Pérez",
        "codigo_cliente": "C-0000123",
    }
    for field, value in extra_pii.items():
        with pytest.raises(Exception):
            Complaint(**_kwargs(**{field: value}))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kwargs(**overrides) -> dict:
    base = dict(
        complaint_id="BCO-2026-000017",
        institution_id="SBS-001234",
        received_date="2026-05-12",
        complainant_doc_type="DNI",
        product_category="TARJETA_CREDITO",
        channel="APP_MOVIL",
        motivo_code="COBRO_INDEBIDO",
        severity="HIGH",
        description_text=(
            "Se realizó un cargo no autorizado por S/ 245.00 en la tarjeta "
            "de crédito el 10 de mayo."
        ),
        description_language="es",
        complainant_age_range="35_44",
        complainant_district="1501",
        submission_method="APP_MOVIL",
        original_reference_id=None,
        resolution_status="pendiente",
    )
    base.update(overrides)
    return base
