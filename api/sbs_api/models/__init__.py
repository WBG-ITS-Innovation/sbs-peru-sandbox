"""Pydantic v2 models for the SBS SupTech API.

The 15-field complaint subset is defined in :mod:`sbs_api.models.anexo_1a`.
Wire envelopes (requests, responses, batch manifests, problem details) live in
:mod:`sbs_api.models.requests` and :mod:`sbs_api.models.responses`.

The OpenAPI specification at ``api/openapi/sbs-api-v1.yaml`` is the canonical
contract (ADR 0027). These models implement it. ``tests/test_openapi_pydantic_match.py``
enforces alignment.
"""

from sbs_api.models.anexo_1a import (
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
from sbs_api.models.requests import (
    BatchManifest,
    ComplaintQuery,
    ComplaintStatusPatch,
    ComplaintSubmission,
)
from sbs_api.models.responses import (
    BatchRejectionsResponse,
    BatchRowRejectionDetail,
    BatchStatus,
    BatchSubmission,
    ComplaintCreated,
    ComplaintListItem,
    ComplaintListResponse,
    HealthStatus,
    InstitutionStatus,
    ProblemDetail,
    SupervisoryMetadata,
    VersionInfo,
)

__all__ = [
    # taxonomy enums
    "Channel",
    "ComplainantAgeRange",
    "ComplainantDocType",
    "DescriptionLanguage",
    "MotivoCode",
    "ProductCategory",
    "ResolutionStatus",
    "Severity",
    "SubmissionMethod",
    # core complaint
    "Complaint",
    # requests
    "BatchManifest",
    "ComplaintQuery",
    "ComplaintStatusPatch",
    "ComplaintSubmission",
    # responses
    "BatchRejectionsResponse",
    "BatchRowRejectionDetail",
    "BatchStatus",
    "BatchSubmission",
    "ComplaintCreated",
    "ComplaintListItem",
    "ComplaintListResponse",
    "HealthStatus",
    "InstitutionStatus",
    "ProblemDetail",
    "SupervisoryMetadata",
    "VersionInfo",
]
