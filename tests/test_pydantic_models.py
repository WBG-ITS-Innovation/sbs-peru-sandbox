"""Tests for the Pydantic v2 models in sbs_api.models.

Covers: happy-path construction, per-field validator failures, and the one
cross-field rule (original_reference_id != complaint_id), plus the
ComplaintStatusPatch terminal-state reason-required rule.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from sbs_api.models import (
    BatchManifest,
    Complaint,
    ComplaintStatusPatch,
    ComplaintSubmission,
    ProblemDetail,
    ResolutionStatus,
)


VALID_COMPLAINT_KWARGS = dict(
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
    complainant_district="150100",
    submission_method="APP_MOVIL",
    original_reference_id=None,
    resolution_status="pendiente",
)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_complaint_constructs_from_valid_kwargs():
    c = Complaint(**VALID_COMPLAINT_KWARGS)
    assert c.complaint_id == "BCO-2026-000017"
    assert c.institution_id == "SBS-001234"
    assert c.received_date == date(2026, 5, 12)
    assert c.resolution_status == "pendiente"


def test_complaint_round_trips_through_json():
    c = Complaint(**VALID_COMPLAINT_KWARGS)
    blob = c.model_dump_json()
    c2 = Complaint.model_validate_json(blob)
    assert c.model_dump() == c2.model_dump()


def test_complaint_submission_wraps_complaint():
    sub = ComplaintSubmission(
        complaint=VALID_COMPLAINT_KWARGS,
        client_submission_id="sub-2026-05-12-abc12345",
    )
    assert sub.complaint.complaint_id == "BCO-2026-000017"
    assert sub.client_submission_id == "sub-2026-05-12-abc12345"


def test_complaint_submission_accepts_null_client_submission_id():
    sub = ComplaintSubmission(complaint=VALID_COMPLAINT_KWARGS)
    assert sub.client_submission_id is None


# ---------------------------------------------------------------------------
# Per-field validators
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "complaint_id",
    [
        "lowercase-2026-000001",
        "BCO_2026_000001",
        "BCO-26-000001",  # 2-digit year
        "BCO-2026-12345",  # only 5 digits
        "AAAAA-2026-000001",  # 5-char prefix
        "",
    ],
)
def test_complaint_id_pattern_rejects_invalid(complaint_id: str):
    kwargs = dict(VALID_COMPLAINT_KWARGS, complaint_id=complaint_id)
    with pytest.raises(ValidationError):
        Complaint(**kwargs)


@pytest.mark.parametrize(
    "institution_id",
    ["sbs-001234", "SBS001234", "SBS-12", "SBS-1234567", "SBS-ABCD"],
)
def test_institution_id_pattern_rejects_invalid(institution_id: str):
    kwargs = dict(VALID_COMPLAINT_KWARGS, institution_id=institution_id)
    with pytest.raises(ValidationError):
        Complaint(**kwargs)


def test_district_zero_rejected():
    kwargs = dict(VALID_COMPLAINT_KWARGS, complainant_district="000000")
    with pytest.raises(ValidationError) as exc_info:
        Complaint(**kwargs)
    assert "000000" in str(exc_info.value)


def test_district_pattern_rejects_non_digits():
    kwargs = dict(VALID_COMPLAINT_KWARGS, complainant_district="XYZABC")
    with pytest.raises(ValidationError):
        Complaint(**kwargs)


def test_district_pattern_rejects_wrong_length():
    # 4 digits used to be valid; now the canonical INEI ubigeo is 6 digits.
    kwargs = dict(VALID_COMPLAINT_KWARGS, complainant_district="1501")
    with pytest.raises(ValidationError):
        Complaint(**kwargs)


def test_district_pattern_rejects_five_digits():
    kwargs = dict(VALID_COMPLAINT_KWARGS, complainant_district="15010")
    with pytest.raises(ValidationError):
        Complaint(**kwargs)


def test_district_pattern_accepts_canonical_six_digit_ubigeo():
    # Lima/Lima with district unspecified per dept+prov precision rule.
    kwargs = dict(VALID_COMPLAINT_KWARGS, complainant_district="150100")
    Complaint(**kwargs)


def test_district_pattern_accepts_abroad_sentinel():
    kwargs = dict(VALID_COMPLAINT_KWARGS, complainant_district="999999")
    Complaint(**kwargs)


def test_description_too_short_is_rejected():
    kwargs = dict(VALID_COMPLAINT_KWARGS, description_text="too short")
    with pytest.raises(ValidationError):
        Complaint(**kwargs)


def test_description_with_control_characters_is_rejected():
    kwargs = dict(
        VALID_COMPLAINT_KWARGS,
        description_text="Valid prefix\x07with-bell-control-char",
    )
    with pytest.raises(ValidationError) as exc_info:
        Complaint(**kwargs)
    assert "control" in str(exc_info.value).lower()


def test_description_allows_normal_whitespace():
    text = "Reclamo con saltos de línea.\nLínea 2.\nLínea 3 con tab\there."
    kwargs = dict(VALID_COMPLAINT_KWARGS, description_text=text)
    Complaint(**kwargs)  # must not raise


def test_unknown_enum_value_is_rejected():
    kwargs = dict(VALID_COMPLAINT_KWARGS, channel="TELEPATHY")
    with pytest.raises(ValidationError):
        Complaint(**kwargs)


def test_extra_field_is_rejected():
    kwargs = dict(VALID_COMPLAINT_KWARGS, mystery_field="surprise")
    with pytest.raises(ValidationError):
        Complaint(**kwargs)


# ---------------------------------------------------------------------------
# Cross-field rule
# ---------------------------------------------------------------------------


def test_original_reference_id_must_not_equal_complaint_id():
    kwargs = dict(
        VALID_COMPLAINT_KWARGS,
        original_reference_id="BCO-2026-000017",  # same as complaint_id
    )
    with pytest.raises(ValidationError) as exc_info:
        Complaint(**kwargs)
    assert "original_reference_id" in str(exc_info.value)


def test_original_reference_id_can_be_a_different_complaint_id():
    kwargs = dict(
        VALID_COMPLAINT_KWARGS,
        original_reference_id="BCO-2025-000891",
    )
    c = Complaint(**kwargs)
    assert c.original_reference_id == "BCO-2025-000891"


def test_original_reference_id_optional():
    c = Complaint(**VALID_COMPLAINT_KWARGS)
    assert c.original_reference_id is None


# ---------------------------------------------------------------------------
# ComplaintStatusPatch terminal-state reason-required rule (cross-field)
# ---------------------------------------------------------------------------


def test_status_patch_pendiente_without_reason_is_valid():
    p = ComplaintStatusPatch(resolution_status="pendiente")
    assert p.reason is None


def test_status_patch_pendiente_with_reason_is_valid():
    p = ComplaintStatusPatch(
        resolution_status="pendiente",
        reason="Reabriendo el caso por información adicional del cliente.",
    )
    assert p.reason is not None


def test_status_patch_atendido_without_reason_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        ComplaintStatusPatch(resolution_status="atendido")
    assert "reason" in str(exc_info.value).lower()


def test_status_patch_anulado_without_reason_is_rejected():
    with pytest.raises(ValidationError) as exc_info:
        ComplaintStatusPatch(resolution_status="anulado")
    assert "reason" in str(exc_info.value).lower()


def test_status_patch_atendido_with_reason_is_valid():
    p = ComplaintStatusPatch(
        resolution_status="atendido",
        reason="Cargo revertido el 2026-05-14. Cliente notificado por correo.",
    )
    assert p.resolution_status == "atendido"
    assert p.reason is not None


def test_status_patch_anulado_with_reason_is_valid():
    p = ComplaintStatusPatch(
        resolution_status="anulado",
        reason="Reclamo duplicado del BCO-2026-000016; anulado por consolidación.",
    )
    assert p.resolution_status == "anulado"


def test_status_patch_atendido_with_whitespace_only_reason_is_rejected():
    with pytest.raises(ValidationError):
        ComplaintStatusPatch(
            resolution_status="atendido",
            reason="          ",
        )


# ---------------------------------------------------------------------------
# ProblemDetail (RFC 9457)
# ---------------------------------------------------------------------------


def test_problem_detail_minimal_required_fields():
    pd = ProblemDetail(
        type="https://sbs.gob.pe/errors/SBS-422-001",
        title="Validation failed",
        status=422,
        code="SBS-422-001",
    )
    assert pd.status == 422
    assert pd.code == "SBS-422-001"


def test_problem_detail_code_pattern_enforced():
    with pytest.raises(ValidationError):
        ProblemDetail(
            type="https://sbs.gob.pe/errors/wrong-format",
            title="bad",
            status=400,
            code="WRONG-FORMAT",
        )


def test_problem_detail_status_range_enforced():
    with pytest.raises(ValidationError):
        ProblemDetail(
            type="https://sbs.gob.pe/errors/SBS-200-001",
            title="not an error",
            status=200,
            code="SBS-200-001",
        )


# ---------------------------------------------------------------------------
# BatchManifest
# ---------------------------------------------------------------------------


VALID_MANIFEST_KWARGS = dict(
    reporting_period_start="2026-05-01",
    reporting_period_end="2026-05-31",
    schema_version="v0.1.0",
    row_count_submitted=412,
    checksum_sha256="cafebabecafebabecafebabecafebabecafebabecafebabecafebabecafebabe",
)


def test_batch_manifest_happy_path():
    m = BatchManifest(**VALID_MANIFEST_KWARGS)
    assert m.row_count_submitted == 412
    assert m.schema_version == "v0.1.0"


def test_batch_manifest_rejects_short_checksum():
    kwargs = dict(VALID_MANIFEST_KWARGS, checksum_sha256="deadbeef")
    with pytest.raises(ValidationError):
        BatchManifest(**kwargs)


def test_batch_manifest_rejects_uppercase_checksum():
    kwargs = dict(
        VALID_MANIFEST_KWARGS,
        checksum_sha256="CAFEBABECAFEBABECAFEBABECAFEBABECAFEBABECAFEBABECAFEBABECAFEBABE",
    )
    with pytest.raises(ValidationError):
        BatchManifest(**kwargs)


def test_batch_manifest_rejects_bad_schema_version():
    kwargs = dict(VALID_MANIFEST_KWARGS, schema_version="0.1.0")  # missing 'v'
    with pytest.raises(ValidationError):
        BatchManifest(**kwargs)


def test_batch_manifest_rejects_inverted_period():
    kwargs = dict(
        VALID_MANIFEST_KWARGS,
        reporting_period_start="2026-12-31",
        reporting_period_end="2026-01-01",
    )
    with pytest.raises(ValidationError):
        BatchManifest(**kwargs)


def test_batch_manifest_schema_version_optional():
    kwargs = dict(VALID_MANIFEST_KWARGS)
    kwargs.pop("schema_version")
    m = BatchManifest(**kwargs)
    assert m.schema_version is None


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------


def test_resolution_status_values_match_resolucion():
    assert ResolutionStatus.PENDIENTE.value == "pendiente"
    assert ResolutionStatus.ATENDIDO.value == "atendido"
    assert ResolutionStatus.ANULADO.value == "anulado"
