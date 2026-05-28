"""Python exception classes that map to RFC 9457 ProblemDetail responses.

Each subclass carries the stable `code` (matching `api/openapi/error-catalog.md`),
the HTTP status, the human-readable title, and an optional `detail`. The
handler in :mod:`sbs_api.errors.handlers` converts the exception into the
RFC 9457 envelope at response time.

Why subclass-based, not factory-based: the FastAPI exception-handler
registry is keyed on exception class, so subclassing is the idiomatic path.
"""

from __future__ import annotations

from typing import Any


class SBSAPIException(Exception):
    """Base class for every domain exception that should produce a ProblemDetail.

    Subclasses set the class-level attributes. The constructor accepts an
    optional ``detail`` string and an optional ``errors`` list of field-level
    failures (used by validation paths).

    ``extra_headers`` is the rate-limiter's seam: a subclass that wants
    extra response headers (e.g. Retry-After, X-RateLimit-*) on the
    materialised ProblemDetail can populate it via ``__init__``. The
    exception handler merges it into the response.
    """

    code: str = "SBS-500-001"
    status: int = 500
    title: str = "Internal server error"
    type_suffix: str = "SBS-500-001"

    def __init__(
        self,
        detail: str | None = None,
        *,
        errors: list[dict[str, Any]] | None = None,
        instance: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        self.errors = errors
        self.instance = instance
        self.extra_headers = extra_headers or {}


class ResourceNotFound(SBSAPIException):
    code = "SBS-404-001"
    status = 404
    title = "Resource not found"
    type_suffix = "SBS-404-001"


class TenantMismatch(SBSAPIException):
    """Returned to clients as 404 (not 403) so existence is not leaked across tenants."""

    code = "SBS-404-001"
    status = 404
    title = "Resource not found"
    type_suffix = "SBS-404-001"


class InstitutionNotFound(SBSAPIException):
    """The institution_id referenced by the request is not registered.

    Distinct from :class:`ResourceNotFound` because the error-catalog
    entry SBS-404-003 carries a different remediation path: the integrator
    needs to verify the institution_id against SBS's published list, not
    check whether the resource exists for their tenant.
    """

    code = "SBS-404-003"
    status = 404
    title = "Institution not found"
    type_suffix = "SBS-404-003"


class DuplicateComplaintId(SBSAPIException):
    """A complaint with the same complaint_id already exists for this institution.

    Mapped from the database PK collision (``complaints_pkey``) at the
    INSERT path. The error-catalog remediation steers the integrator to
    either pick a fresh complaint_id or, if the re-submission was
    intentional, use idempotency replay (same Idempotency-Key).
    """

    code = "SBS-409-001"
    status = 409
    title = "Duplicate complaint_id"
    type_suffix = "SBS-409-001"


class ResolutionStatusTransitionForbidden(SBSAPIException):
    code = "SBS-422-004"
    status = 422
    title = "Resolution status transition forbidden"
    type_suffix = "RESOLUTION_STATUS_TRANSITION_FORBIDDEN"


class ETagMismatch(SBSAPIException):
    code = "SBS-412-001"
    status = 412
    title = "ETag mismatch"
    type_suffix = "ETAG_MISMATCH"


class PreconditionRequired(SBSAPIException):
    code = "SBS-428-001"
    status = 428
    title = "Precondition required"
    type_suffix = "SBS-428-001"


class IdempotencyKeyReuseWithDifferentBody(SBSAPIException):
    code = "SBS-409-002"
    status = 409
    title = "Idempotency-Key reused with different body"
    type_suffix = "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_BODY"


class IdempotencyKeyInFlight(SBSAPIException):
    """Concurrent duplicate POST (ADR 0029 amendment).

    A second request with the same ``Idempotency-Key`` arrived while the
    first is still processing. After waiting up to 150ms for the first
    to complete, the handler gives up and returns 409 so the client
    retries after a brief pause.
    """

    code = "SBS-409-003"
    status = 409
    title = "Idempotency-Key in flight"
    type_suffix = "IDEMPOTENCY_KEY_IN_FLIGHT"


class CursorInvalid(SBSAPIException):
    code = "SBS-400-005"
    status = 400
    title = "Cursor invalid"
    type_suffix = "CURSOR_INVALID"


class RequestBodyTooLarge(SBSAPIException):
    code = "SBS-400-004"
    status = 413
    title = "Request body too large"
    type_suffix = "REQUEST_BODY_TOO_LARGE"


class BatchFileTooLarge(SBSAPIException):
    """Tier 2 multipart upload exceeded the per-endpoint CSV size cap.

    Distinct from :class:`RequestBodyTooLarge` so the integrator's error
    handler can branch on the code: a 413 on `/v1/complaints` means the
    JSON payload was malformed; a 413 on `/v1/batches` means the CSV file
    itself was too large and the institution should split the batch.
    """

    code = "SBS-413-002"
    status = 413
    title = "Batch file too large"
    type_suffix = "BATCH_FILE_TOO_LARGE"


class BatchManifestInvalid(SBSAPIException):
    """Manifest JSON shape or content failed validation.

    Covers: missing required fields, malformed JSON, period start after
    end, row count out of range. Distinct from BATCH_CHECKSUM_MISMATCH
    which is a content-vs-claim disagreement.
    """

    code = "SBS-400-006"
    status = 400
    title = "Batch manifest invalid"
    type_suffix = "BATCH_MANIFEST_INVALID"


class BatchChecksumMismatch(SBSAPIException):
    """Manifest's `checksum_sha256` does not match the actually-received CSV bytes."""

    code = "SBS-400-007"
    status = 400
    title = "Batch checksum mismatch"
    type_suffix = "BATCH_CHECKSUM_MISMATCH"


class WebhookUrlRejected(SBSAPIException):
    """Outbound webhook URL failed validation (HTTPS / FQDN / public-IP).

    Surfaces in webhook_deliveries.failure_reason; not directly raised by
    a request handler. Defined here so the error catalog has a stable
    code for ops dashboards that surface delivery failures.
    """

    code = "SBS-403-020"
    status = 403
    title = "Webhook URL rejected by validation"
    type_suffix = "WEBHOOK_URL_REJECTED"


class AuthenticationNotConfigured(SBSAPIException):
    code = "SBS-503-002"
    status = 503
    title = "Authentication not configured"
    type_suffix = "AUTH_NOT_CONFIGURED"


class ServiceUnavailable(SBSAPIException):
    code = "SBS-503-001"
    status = 503
    title = "Service degraded or down"
    type_suffix = "SBS-503-001"


class CircuitBreakerPaused(SBSAPIException):
    """Ingestion for this institution is paused by an SBS IT circuit breaker
    (P-RESHAPE-9). The integrator should retry after SBS resumes ingestion."""

    code = "SBS-503-003"
    status = 503
    title = "Ingestion paused for institution"
    type_suffix = "fi_circuit_breaker_paused"


# --- mTLS (ADR 0031) ------------------------------------------------------


class CertRequired(SBSAPIException):
    code = "SBS-401-001"
    status = 401
    title = "Client certificate required"
    type_suffix = "CERT_REQUIRED"


class CertInvalid(SBSAPIException):
    code = "SBS-401-002"
    status = 401
    title = "Client certificate invalid"
    type_suffix = "CERT_INVALID"


class CertExpired(SBSAPIException):
    code = "SBS-401-003"
    status = 401
    title = "Client certificate expired"
    type_suffix = "CERT_EXPIRED"


class CertCnUnknown(SBSAPIException):
    code = "SBS-403-001"
    status = 403
    title = "Client certificate CN not registered"
    type_suffix = "CERT_CN_UNKNOWN"


class CertRevoked(SBSAPIException):
    code = "SBS-403-002"
    status = 403
    title = "Client certificate revoked"
    type_suffix = "CERT_REVOKED"


# --- HMAC request signing (ADR 0027 amendment) ----------------------------


class SignatureMissingHeader(SBSAPIException):
    code = "SBS-401-010"
    status = 401
    title = "HMAC signature header missing"
    type_suffix = "SIGNATURE_MISSING_HEADER"


class SignatureAlgorithmUnsupported(SBSAPIException):
    code = "SBS-401-011"
    status = 401
    title = "HMAC signature algorithm unsupported"
    type_suffix = "SIGNATURE_ALGORITHM_UNSUPPORTED"


class SignatureInvalid(SBSAPIException):
    code = "SBS-401-012"
    status = 401
    title = "HMAC signature invalid"
    type_suffix = "SIGNATURE_INVALID"


class SignatureExpired(SBSAPIException):
    code = "SBS-401-013"
    status = 401
    title = "HMAC signature timestamp out of window"
    type_suffix = "SIGNATURE_EXPIRED"


class SignatureReplayed(SBSAPIException):
    code = "SBS-401-014"
    status = 401
    title = "HMAC signature already seen within replay window"
    type_suffix = "SIGNATURE_REPLAYED"


class SignatureInstitutionMismatch(SBSAPIException):
    code = "SBS-401-015"
    status = 401
    title = "HMAC institution_id does not match mTLS subject"
    type_suffix = "SIGNATURE_INSTITUTION_MISMATCH"


class HmacSecretNotConfigured(SBSAPIException):
    """Server-side: institution has no row in institution_secrets."""

    code = "SBS-503-003"
    status = 503
    title = "HMAC secret not configured for institution"
    type_suffix = "HMAC_SECRET_NOT_CONFIGURED"


# --- OAuth 2.0 client_credentials (ADR 0032) -----------------------------


class TokenRequired(SBSAPIException):
    code = "SBS-401-020"
    status = 401
    title = "OAuth access token required"
    type_suffix = "TOKEN_REQUIRED"


class TokenInvalid(SBSAPIException):
    code = "SBS-401-021"
    status = 401
    title = "OAuth access token invalid"
    type_suffix = "TOKEN_INVALID"


class TokenExpired(SBSAPIException):
    code = "SBS-401-022"
    status = 401
    title = "OAuth access token expired"
    type_suffix = "TOKEN_EXPIRED"


class TokenCertThumbprintMismatch(SBSAPIException):
    code = "SBS-401-023"
    status = 401
    title = "OAuth token cert thumbprint mismatch"
    type_suffix = "TOKEN_CERT_THUMBPRINT_MISMATCH"


class TokenScopeInsufficient(SBSAPIException):
    code = "SBS-403-010"
    status = 403
    title = "OAuth token scope insufficient"
    type_suffix = "TOKEN_SCOPE_INSUFFICIENT"


class TokenCertRequired(SBSAPIException):
    """Token endpoint hit without a valid mTLS connection."""

    code = "SBS-401-024"
    status = 401
    title = "OAuth token request requires mTLS"
    type_suffix = "TOKEN_CERT_REQUIRED"


class OAuthInvalidScope(SBSAPIException):
    """Per RFC 6749 §5.2 — requested ∩ permitted is empty."""

    code = "SBS-400-010"
    status = 400
    title = "OAuth invalid_scope"
    type_suffix = "INVALID_SCOPE"


class OAuthInvalidGrant(SBSAPIException):
    """Per RFC 6749 §5.2 — client credentials invalid."""

    code = "SBS-401-025"
    status = 401
    title = "OAuth invalid_grant"
    type_suffix = "INVALID_GRANT"


class OAuthInvalidRequest(SBSAPIException):
    """Per RFC 6749 §5.2 — request shape malformed."""

    code = "SBS-400-011"
    status = 400
    title = "OAuth invalid_request"
    type_suffix = "INVALID_REQUEST"


# --- Rate limiting (ADR 0033) ---------------------------------------------


class RateLimitExceeded(SBSAPIException):
    """Business-bucket overrun: institution exceeded its per-minute limit."""

    code = "SBS-429-001"
    status = 429
    title = "Rate limit exceeded"
    type_suffix = "RATE_LIMIT_EXCEEDED"


class TokenEndpointRateLimitExceeded(SBSAPIException):
    """Token-endpoint bucket overrun (pressure-test amendment to ADR 0033)."""

    code = "SBS-429-002"
    status = 429
    title = "OAuth token endpoint rate limit exceeded"
    type_suffix = "TOKEN_ENDPOINT_RATE_LIMIT_EXCEEDED"
