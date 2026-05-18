"""RFC 9457 problem+json exception classes and FastAPI handlers.

Application code raises subclasses of :class:`SBSAPIException` rather than
returning ``JSONResponse(...)`` directly. A single handler registered on the
app translates each subclass into the canonical RFC 9457 envelope and
attaches the OpenTelemetry trace_id.
"""

from sbs_api.errors.exceptions import (
    AuthenticationNotConfigured,
    CursorInvalid,
    DuplicateComplaintId,
    ETagMismatch,
    IdempotencyKeyReuseWithDifferentBody,
    InstitutionNotFound,
    PreconditionRequired,
    RequestBodyTooLarge,
    ResolutionStatusTransitionForbidden,
    ResourceNotFound,
    SBSAPIException,
    ServiceUnavailable,
    TenantMismatch,
)

__all__ = [
    "AuthenticationNotConfigured",
    "CursorInvalid",
    "DuplicateComplaintId",
    "ETagMismatch",
    "IdempotencyKeyReuseWithDifferentBody",
    "InstitutionNotFound",
    "PreconditionRequired",
    "RequestBodyTooLarge",
    "ResolutionStatusTransitionForbidden",
    "ResourceNotFound",
    "SBSAPIException",
    "ServiceUnavailable",
    "TenantMismatch",
]
