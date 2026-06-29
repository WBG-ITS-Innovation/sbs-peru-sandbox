# SPDX-License-Identifier: Apache-2.0
"""Request envelopes for the SBS SupTech API.

The :class:`ComplaintSubmission` is the body of ``POST /v1/complaints``.
:class:`ComplaintStatusPatch` is the body of the status-update PATCH.
:class:`ComplaintQuery` is the bag of query parameters for ``GET /v1/complaints``.
:class:`BatchManifest` is the metadata-only submission for ``POST /v1/batches``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sbs_api.models.anexo_1a import (
    Channel,
    Complaint,
    MotivoCode,
    ProductCategory,
    ResolutionStatus,
)


class ComplaintSubmission(BaseModel):
    """Body of ``POST /v1/complaints``.

    A direct wrapper around :class:`Complaint` plus an idempotency hint that
    institutions echo for at-least-once delivery semantics. The wire spec
    requires the ``Idempotency-Key`` HTTP header on every POST; the optional
    ``client_submission_id`` here is a *body-level* hint useful for log
    correlation and debugging.
    """

    model_config = ConfigDict(extra="forbid")

    complaint: Complaint = Field(
        ...,
        description="The Anexo 1-A 15-field complaint payload.",
    )
    client_submission_id: str | None = Field(
        default=None,
        min_length=8,
        max_length=64,
        description=(
            "Optional. An institution-side correlation identifier echoed back "
            "in the 201 response and in the audit log. Distinct from the "
            "Idempotency-Key HTTP header which is required for at-least-once "
            "POST semantics."
        ),
        examples=["sub-2026-05-12-abc123"],
    )


class ComplaintStatusPatch(BaseModel):
    """Body of ``PATCH /v1/complaints/{complaint_id}/status``.

    Only the :class:`ResolutionStatus` field is mutable post-creation in the
    May 25 sandbox. The reason field is required when transitioning to
    'atendido' or 'anulado'; the model-level validator below enforces this.
    Violations are reported as SBS-422-002 by the error catalog.
    """

    model_config = ConfigDict(extra="forbid")

    resolution_status: ResolutionStatus = Field(
        ...,
        description="New resolution status. Must differ from the current state.",
    )
    reason: str | None = Field(
        default=None,
        min_length=10,
        max_length=2000,
        description=(
            "Required when transitioning to 'atendido' or 'anulado'. Free "
            "text capturing the rationale; recorded in the audit log."
        ),
    )

    @model_validator(mode="after")
    def _reason_required_on_terminal_states(self) -> "ComplaintStatusPatch":
        terminal = {ResolutionStatus.ATENDIDO, ResolutionStatus.ANULADO}
        # `use_enum_values` is not set on this model, so resolution_status is
        # a ResolutionStatus member. Compare to the enum members directly.
        if self.resolution_status in terminal and (
            self.reason is None or len(self.reason.strip()) < 10
        ):
            raise ValueError(
                "reason is required (>=10 non-whitespace chars) when "
                "transitioning resolution_status to 'atendido' or 'anulado'"
            )
        return self


class ComplaintQuery(BaseModel):
    """Query parameters for ``GET /v1/complaints``.

    All filters are optional and combined with AND semantics. Pagination is
    cursor-based; institutions pass the ``next_cursor`` echoed in the
    previous response.
    """

    model_config = ConfigDict(extra="forbid")

    institution_id: str | None = Field(
        default=None,
        pattern=r"^SBS-\d{4,6}$",
        description=(
            "Filter by institution. SBS supervisor users may scope queries "
            "across institutions; institution users see only their own."
        ),
    )
    received_date_from: date | None = Field(
        default=None,
        description="Inclusive lower bound on received_date.",
    )
    received_date_to: date | None = Field(
        default=None,
        description="Inclusive upper bound on received_date.",
    )
    product_category: ProductCategory | None = None
    channel: Channel | None = None
    motivo_code: MotivoCode | None = None
    resolution_status: ResolutionStatus | None = None
    page_size: Annotated[int, Field(ge=1, le=200)] = 50
    next_cursor: str | None = Field(
        default=None,
        min_length=8,
        max_length=256,
        description=(
            "Opaque pagination cursor. Pass the value from the previous "
            "response's `next_cursor` field. Omit on the first page."
        ),
    )


class BatchManifest(BaseModel):
    """Manifest part of a ``POST /v1/batches`` multipart upload (ADR 0034).

    Tier 2 batch upload is a one-shot multipart request: the manifest JSON
    and the CSV file ride together. The institution_id is *not* in the
    manifest — the server reads it from the OAuth token and the mTLS
    subject, both of which are already authenticated. The file name is
    carried in the multipart `Content-Disposition: filename=` header, not
    a manifest field. Both reductions remove the redundant fields the
    Prompt 5/6 metadata-only scaffold required.
    """

    model_config = ConfigDict(extra="forbid")

    reporting_period_start: date = Field(
        ...,
        description="Inclusive start of the reporting period covered by this batch.",
    )
    reporting_period_end: date = Field(
        ...,
        description="Inclusive end of the reporting period covered by this batch.",
    )
    row_count_submitted: int = Field(
        ...,
        ge=1,
        le=1_000_000,
        description=(
            "Number of complaint rows the institution claims are in the CSV. "
            "The server records this for cross-check; the worker counts the "
            "actual rows during processing."
        ),
    )
    checksum_sha256: str = Field(
        ...,
        pattern=r"^[a-f0-9]{64}$",
        description=(
            "Lowercase hex SHA-256 of the CSV file bytes the institution is "
            "uploading. The server recomputes on receipt and rejects with "
            "BATCH_CHECKSUM_MISMATCH on disagreement. Also the body-hash "
            "input for the HMAC canonical request per ADR 0027 amendment "
            "(multipart body-hash definition: CSV bytes only)."
        ),
        examples=[
            # Repeating cafebabe — clearly illustrative, not a real hash.
            "cafebabecafebabecafebabecafebabecafebabecafebabecafebabecafebabe"
        ],
    )
    schema_version: str | None = Field(
        default=None,
        pattern=r"^v\d+\.\d+\.\d+$",
        description=(
            "Optional. Anexo 1-A schema version the institution is targeting. "
            "Defaults to the server's current schema_version when omitted. "
            "Specifying it explicitly lets the server reject a batch built "
            "against a different schema with a clearer error than per-row "
            "validation failures."
        ),
        examples=["v0.1.0"],
    )

    @model_validator(mode="after")
    def _reporting_period_ordered(self) -> "BatchManifest":
        if self.reporting_period_end < self.reporting_period_start:
            raise ValueError(
                "reporting_period_end must be on or after reporting_period_start"
            )
        return self
