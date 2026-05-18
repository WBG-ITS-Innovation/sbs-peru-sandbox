"""Anexo 1-A complaint taxonomy — 15-field curated subset for May 25 sandbox.

The 15 fields below are reconciled against Anexo N° 1-A of Resolución SBS
N° 04036-2022 (Reglamento de Gestión de Reclamos y Requerimientos). The full
mapping — including the three fields that have no Anexo 1-A counterpart and
the four PII-bearing Anexo 1-A fields deliberately excluded from the May 25
sandbox — is recorded in ADR 0026.

The code-list enums (channel, product category, motivo, district) carry a
representative subset of the codes in the resolución's Anexos A through D.
The full code lists are deferred to Part 11 standards-pack distribution; see
PLAN.md Part 11.

This module imports no FastAPI symbols. It is pure data definition.
"""

from __future__ import annotations

import re
from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Taxonomy enums
# ---------------------------------------------------------------------------


class ComplainantDocType(str, Enum):
    """Document-type code identifying the complainant — Resolución Anexo 1-A #2.

    A representative subset of Anexo A document-type codes. The doc type acts
    as a proxy for natural-vs-juridic person classification (DNI/CE/PASS imply
    natural persons; RUC implies a juridic person).
    """

    DNI = "DNI"
    CE = "CE"
    PASAPORTE = "PASAPORTE"
    RUC = "RUC"
    OTRO = "OTRO"


class ProductCategory(str, Enum):
    """Product / service / operation category — Resolución Anexo 1-A #14 (Anexo B).

    Representative subset. The full Anexo B code list is deferred to Part 11.
    """

    DEPOSITOS = "DEPOSITOS"
    CREDITOS = "CREDITOS"
    TARJETA_CREDITO = "TARJETA_CREDITO"
    TARJETA_DEBITO = "TARJETA_DEBITO"
    SEGUROS = "SEGUROS"
    AFP_PENSIONES = "AFP_PENSIONES"
    COOPAC = "COOPAC"
    OTRO = "OTRO"


class Channel(str, Enum):
    """Channel through which the complaint was registered — Resolución Anexo 1-A #7 (Anexo A).

    Representative subset of Anexo A channel codes.
    """

    AGENCIA = "AGENCIA"
    WEB = "WEB"
    APP_MOVIL = "APP_MOVIL"
    TELEFONO = "TELEFONO"
    CORREO = "CORREO"
    PRESENCIAL_SBS = "PRESENCIAL_SBS"
    OTRO = "OTRO"


class SubmissionMethod(str, Enum):
    """Channel through which the underlying operation occurred — Resolución Anexo 1-A #8.

    Distinct from :class:`Channel` (which records where the complaint was
    *registered*). Representative subset of Anexo A operation channels.
    """

    AGENCIA = "AGENCIA"
    CAJERO = "CAJERO"
    APP_MOVIL = "APP_MOVIL"
    WEB = "WEB"
    POS = "POS"
    AGENTE_CORRESPONSAL = "AGENTE_CORRESPONSAL"
    OTRO = "OTRO"


class MotivoCode(str, Enum):
    """Motivo del reclamo — Resolución Anexo 1-A #15 (Anexo C).

    Representative subset of Anexo C motivos. The full code list is deferred
    to Part 11.
    """

    COBRO_INDEBIDO = "COBRO_INDEBIDO"
    OPERACION_NO_RECONOCIDA = "OPERACION_NO_RECONOCIDA"
    DEMORA_ATENCION = "DEMORA_ATENCION"
    INFORMACION_INCORRECTA = "INFORMACION_INCORRECTA"
    INCUMPLIMIENTO_CONTRATO = "INCUMPLIMIENTO_CONTRATO"
    CALIDAD_SERVICIO = "CALIDAD_SERVICIO"
    PUBLICIDAD_ENGANOSA = "PUBLICIDAD_ENGANOSA"
    OTRO = "OTRO"


class Severity(str, Enum):
    """Severity tag set by the institution at submission time.

    No counterpart in Anexo 1-A; this is a prototype-level field used by the
    supervisory agents (Part 5+) for triage. See ADR 0026 for the divergence
    rationale.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DescriptionLanguage(str, Enum):
    """ISO 639-1 / ISO 639-3 language code for the complaint narrative.

    No counterpart in Anexo 1-A. Included to handle Quechua / Aymara / English
    narratives that may appear in the Peruvian context. See ADR 0026.
    """

    ES = "es"
    QU = "qu"
    AY = "ay"
    EN = "en"


class ComplainantAgeRange(str, Enum):
    """Age range bucket of the complainant.

    No counterpart in Anexo 1-A. Used in lieu of the resolución's PII-bearing
    fields (DNI, full name) for the May 25 sandbox. See ADR 0026.
    """

    UNDER_25 = "UNDER_25"
    R_25_34 = "25_34"
    R_35_44 = "35_44"
    R_45_54 = "45_54"
    R_55_64 = "55_64"
    OVER_64 = "OVER_64"
    UNKNOWN = "UNKNOWN"


class ResolutionStatus(str, Enum):
    """Estado del reclamo — Resolución Anexo 1-A #22.

    Resolución values: ``pendiente``, ``atendido``, ``anulado``. Mirrored here
    in lowercase to match the resolución wording.
    """

    PENDIENTE = "pendiente"
    ATENDIDO = "atendido"
    ANULADO = "anulado"


# ---------------------------------------------------------------------------
# Field-level patterns
# ---------------------------------------------------------------------------


COMPLAINT_ID_PATTERN = r"^[A-Z0-9]{1,4}-\d{4}-\d{6,10}$"
INSTITUTION_ID_PATTERN = r"^SBS-\d{4,6}$"
# INEI ubigeo: 6 digits, DDPPDD = department + province + district.
# District digits may be '00' when only department + province is known per the
# resolución's department+province precision requirement. '999999' is the
# documented value for complaints submitted from abroad.
UBIGEO_PATTERN = r"^\d{6}$"


# ---------------------------------------------------------------------------
# Core complaint model
# ---------------------------------------------------------------------------


class Complaint(BaseModel):
    """The 15-field complaint payload as submitted by a supervised institution.

    Field reconciliation against Resolución SBS N° 04036-2022 Anexo 1-A is
    documented in ADR 0026 (Field-by-field reconciliation).
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        use_enum_values=True,
        json_schema_extra={
            "examples": [
                {
                    "complaint_id": "BCO-2026-000017",
                    "institution_id": "SBS-001234",
                    "received_date": "2026-05-12",
                    "complainant_doc_type": "DNI",
                    "product_category": "TARJETA_CREDITO",
                    "channel": "APP_MOVIL",
                    "motivo_code": "COBRO_INDEBIDO",
                    "severity": "HIGH",
                    "description_text": (
                        "Se realizó un cargo no autorizado por S/ 245.00 en "
                        "la tarjeta de crédito el 10 de mayo. El cliente "
                        "solicita reversa inmediata y revisión del estado de "
                        "cuenta."
                    ),
                    "description_language": "es",
                    "complainant_age_range": "35_44",
                    "complainant_district": "150100",
                    "submission_method": "APP_MOVIL",
                    "original_reference_id": None,
                    "resolution_status": "pendiente",
                }
            ]
        },
    )

    complaint_id: str = Field(
        ...,
        min_length=6,
        max_length=32,
        pattern=COMPLAINT_ID_PATTERN,
        description=(
            "Anexo 1-A #1 — Código del reclamo. Stable institution-assigned "
            "identifier. Pattern: institution-prefix, year, sequence."
        ),
        examples=["BCO-2026-000017"],
    )
    institution_id: str = Field(
        ...,
        min_length=8,
        max_length=10,
        pattern=INSTITUTION_ID_PATTERN,
        description=(
            "SBS-assigned institution code (the Empresa código referenced "
            "by the resolución's Reportes section). Format: SBS-NNNN."
        ),
        examples=["SBS-001234"],
    )
    received_date: date = Field(
        ...,
        description=(
            "Anexo 1-A #6 — Fecha de ingreso. The date on which the user "
            "submitted the complaint. ISO-8601 date (YYYY-MM-DD)."
        ),
        examples=["2026-05-12"],
    )
    complainant_doc_type: ComplainantDocType = Field(
        ...,
        description=(
            "Anexo 1-A #2 — Tipo de documento de identidad del reclamante. "
            "Subset of Anexo A document-type codes. Acts as a proxy for "
            "natural-vs-juridic person classification."
        ),
        examples=["DNI"],
    )
    product_category: ProductCategory = Field(
        ...,
        description=(
            "Anexo 1-A #14 — Operación / servicio / producto del reclamo. "
            "Subset of Anexo B codes; full list deferred to Part 11."
        ),
        examples=["TARJETA_CREDITO"],
    )
    channel: Channel = Field(
        ...,
        description=(
            "Anexo 1-A #7 — Canal de ingreso. The channel through which the "
            "user registered the complaint with the institution. Subset of "
            "Anexo A channel codes."
        ),
        examples=["APP_MOVIL"],
    )
    motivo_code: MotivoCode = Field(
        ...,
        description=(
            "Anexo 1-A #15 — Motivo del reclamo SBS. Subset of Anexo C codes; "
            "full list deferred to Part 11."
        ),
        examples=["COBRO_INDEBIDO"],
    )
    severity: Severity = Field(
        ...,
        description=(
            "Severity tag set by the institution. No counterpart in Anexo 1-A; "
            "this is a prototype divergence used by the supervisory agents "
            "(Part 5+) for triage. See ADR 0026."
        ),
        examples=["HIGH"],
    )
    description_text: str = Field(
        ...,
        min_length=10,
        max_length=8000,
        description=(
            "Anexo 1-A #17 — Detalle completo de reclamo. The user's literal "
            "complaint statement as recorded by the institution. Free text, "
            "10–8000 characters."
        ),
        examples=[
            "Se realizó un cargo no autorizado por S/ 245.00 en la tarjeta de crédito."
        ],
    )
    description_language: DescriptionLanguage = Field(
        ...,
        description=(
            "ISO 639 language code for description_text. No counterpart in "
            "Anexo 1-A; included to handle non-Spanish narratives. See ADR 0026."
        ),
        examples=["es"],
    )
    complainant_age_range: ComplainantAgeRange = Field(
        ...,
        description=(
            "Bucketed age range of the complainant. No counterpart in Anexo 1-A; "
            "used in lieu of the resolución's PII-bearing identity fields for "
            "the May 25 sandbox. See ADR 0026."
        ),
        examples=["35_44"],
    )
    complainant_district: str = Field(
        ...,
        pattern=UBIGEO_PATTERN,
        description=(
            "Anexo 1-A #13 — Ubicación geográfica. Six-digit INEI ubigeo "
            "(DDPPDD: department + province + district). The May 25 sandbox "
            "accepts the canonical 6-digit form; district digits may be '00' "
            "when only department + province is known per the resolución's "
            "department+province precision requirement. Example: 150100 = "
            "Lima/Lima with district unspecified. Use '999999' for complaints "
            "submitted from abroad."
        ),
        examples=["150100"],
    )
    submission_method: SubmissionMethod = Field(
        ...,
        description=(
            "Anexo 1-A #8 — Canal de operación. The channel through which the "
            "underlying operation that triggered the complaint occurred. "
            "Distinct from `channel` (which records the complaint-registration "
            "channel). Subset of Anexo A operation channels."
        ),
        examples=["APP_MOVIL"],
    )
    original_reference_id: str | None = Field(
        default=None,
        max_length=32,
        pattern=COMPLAINT_ID_PATTERN,
        description=(
            "Anexo 1-A #23 — Reclamo previo. Optional. When the user is "
            "re-filing a complaint that was previously resolved, this carries "
            "the complaint_id of the prior reclamo (which must also exist in "
            "the institution's database). Same pattern as complaint_id."
        ),
        examples=["BCO-2025-000891"],
    )
    resolution_status: ResolutionStatus = Field(
        ...,
        description=(
            "Anexo 1-A #22 — Estado. Initial state on submission is typically "
            "'pendiente'; 'atendido' or 'anulado' are set via the status "
            "PATCH endpoint over the complaint lifecycle."
        ),
        examples=["pendiente"],
    )

    @field_validator("complainant_district")
    @classmethod
    def _district_not_zero(cls, value: str) -> str:
        if value == "000000":
            raise ValueError(
                "complainant_district '000000' is not a valid INEI ubigeo; use a real "
                "department+province+district code or '999999' for complaints from abroad"
            )
        return value

    @field_validator("description_text")
    @classmethod
    def _description_not_just_whitespace_or_control(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 10:
            raise ValueError(
                "description_text must contain at least 10 non-whitespace characters"
            )
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", value):
            raise ValueError(
                "description_text must not contain control characters (other than "
                "tab/newline/carriage-return)"
            )
        return value

    @model_validator(mode="after")
    def _self_reference_forbidden(self) -> "Complaint":
        # The resolución's #23 says the prior complaint must already exist;
        # we cannot enforce existence in a pure data-model layer, but we can
        # forbid self-reference, which is an unambiguous error.
        if (
            self.original_reference_id is not None
            and self.original_reference_id == self.complaint_id
        ):
            raise ValueError(
                "original_reference_id must not equal complaint_id "
                "(a reclamo cannot reference itself as the prior reclamo)"
            )
        return self
