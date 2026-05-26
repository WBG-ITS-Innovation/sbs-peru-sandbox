"""Pydantic request/response models for the P11A demo ingestion endpoint.

These models are deliberately separate from the institutional
``ComplaintSubmission`` shape: the demo endpoint accepts PII-bearing
fields (full names, DNI, phone, email, account numbers) the
production-shaped Tier 1 endpoint never sees. The demo response is
also a richer envelope — it carries the timeline, the redaction diff,
and the data-quality report so the supervisor UI can render them
without a second round-trip.

ADR 0044 / 0045 record the policy choices these models codify.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class DemoSubmissionRequest(BaseModel):
    """Realistic Anexo-1A-shaped submission with PII fields for demo only.

    Field names follow the Anexo 1-A acronyms where the user-facing
    docs use them; long-form English aliases are accepted on input for
    UI convenience. Validation is intentionally permissive — the
    deterministic data-quality module surfaces issues as errors /
    warnings rather than failing the request.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    institution_id: str = Field(..., min_length=1, max_length=10)
    institution_name: str | None = Field(default=None, max_length=200)

    # COD_REC — the institution's own complaint id.
    institution_complaint_id: str | None = Field(default=None, max_length=64)
    # Optional caller-supplied correlation id.
    client_submission_id: str | None = Field(default=None, max_length=64)

    # Anexo 1-A optional client-identity hints. The demo endpoint
    # stores these only in raw_complaints; canonical complaints never
    # sees them.
    tid_cli: str | None = Field(default=None, max_length=16, description="Anexo 1-A TID_CLI.")
    nro_cli: str | None = Field(default=None, max_length=32, description="Anexo 1-A NRO_CLI.")
    ncl_cli: str | None = Field(default=None, max_length=160, description="Anexo 1-A NCL_CLI.")
    cod_cli: str | None = Field(default=None, max_length=32, description="Anexo 1-A COD_CLI.")

    received_at: str | None = Field(default=None, description="FEC_ING — ISO date or datetime.")
    channel_in: str | None = Field(default=None, description="CNL_ING.")
    channel_operation: str | None = Field(default=None, description="CNL_OPE.")

    product: str | None = Field(default=None, description="PRD_SBS.")
    motive: str | None = Field(default=None, description="MOT_SBS.")
    submotive: str | None = Field(default=None, description="SUB_SBS.")

    narrative: str = Field(..., min_length=1, max_length=8000, description="DET_REC.")
    response_detail: str | None = Field(default=None, max_length=8000, description="DET_RES.")

    amount_claimed: str | None = Field(default=None, description="MNT_REC.")
    status: str | None = Field(default=None, description="EST_REC.")
    previous_complaint_id: str | None = Field(default=None, max_length=64, description="COD_PRV.")
    bancaseguros: str | None = Field(default=None, description="BCA_SEG (field 24).")

    # --- Annex 1-A fields 9 / 10 / 11 / 12 / 13 / 18 / 21 (P11 DQ
    # completion) — all optional in the request model. The DQ engine
    # enforces presence and code-list membership per rule.
    fecha_comunicacion_ampliacion: str | None = Field(
        default=None,
        description="Field 9 — fecha de comunicación de ampliación (ISO 8601 date).",
    )
    canal_comunicacion_ampliacion: str | None = Field(
        default=None,
        description="Field 10 — canal de comunicación de ampliación (Anexo A).",
    )
    fecha_resolucion: str | None = Field(
        default=None,
        description="Field 11 — fecha de resolución (ISO 8601 date).",
    )
    canal_respuesta: str | None = Field(
        default=None,
        description="Field 12 — canal de respuesta del reclamo (Anexo A).",
    )
    ubigeo: str | None = Field(
        default=None,
        max_length=6,
        description="Field 13 — código de ubicación geográfica INEI (4 or 6 digits).",
    )
    resolucion_reclamo: str | None = Field(
        default=None,
        description="Field 18 — favor_usuario / favor_empresa / no_resuelto.",
    )
    nombre_comercial_producto: str | None = Field(
        default=None,
        max_length=200,
        description="Field 21 — nombre comercial del producto o servicio.",
    )
    moneda: str | None = Field(
        default=None,
        max_length=3,
        description="Currency for monto_reclamado — ISO 4217 (PEN/USD/EUR/...).",
    )

    # --- Annex 1-A fields 25 / 26 / 27 (P11 DQ completion — bancaseguros
    # conditional triplet). Required when ``bancaseguros == 'si'``.
    producto_bancaseguros: str | None = Field(
        default=None,
        description="Field 25 — producto bancaseguros (Anexo B Sistema de Seguros).",
    )
    motivo_bancaseguros: str | None = Field(
        default=None,
        description="Field 26 — motivo bancaseguros (Anexo C Sistema de Seguros).",
    )
    submotivo_bancaseguros: str | None = Field(
        default=None,
        description="Field 27 — submotivo bancaseguros (Anexo D Sistema de Seguros).",
    )

    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] | None = Field(
        default=None,
        description="Optional supervisor-facing severity for the demo card.",
    )

    demo_scenario: str | None = Field(
        default=None,
        max_length=64,
        description="Optional label so audit / SSE can correlate runs of the same demo scenario.",
    )


# ---------------------------------------------------------------------------
# Response sub-shapes
# ---------------------------------------------------------------------------


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: str
    at: str
    detail: str | None = None


class RedactionDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    before_masked: str
    after_redacted: str
    policy_version: str
    entities: list[dict[str, Any]]
    entity_count_by_kind: dict[str, int]


class DataQualityEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    suggested_enrichments: list[dict[str, Any]]
    extracted_fields: dict[str, Any]
    policy_version: str


class DemoSubmissionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    complaint_id: str
    raw_complaint_id: str
    institution_id: str
    institution_name: str | None = None
    agent_run_id: str | None = None
    event_id: int | None = None
    timeline: list[TimelineEvent]
    redaction_diff: RedactionDiff
    data_quality: DataQualityEnvelope
