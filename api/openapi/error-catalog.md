# SBS SupTech Complaints API — Error Catalog

This catalog is the canonical list of stable error codes returned by the SBS
SupTech Complaints API. Each error code is paired with an RFC 9457 `type`
URI, an HTTP status, a severity classification, the conditions that produce
it, and remediation guidance.

The `type` URI namespace `https://sbs.gob.pe/errors/{type_suffix}` is a
**placeholder pending SBS sign-off**. Until confirmed, institutions should
treat the `code` field as the stable identifier and the `type` URI as
advisory.
and §2 for the status of namespace confirmation.

Error codes follow the pattern `SBS-<http-status-class>-<sequence>`, where
`<sequence>` is a zero-padded three-digit number unique within the status
class. The HTTP-status-class prefix is the response status for most codes;
historical exceptions (e.g. SBS-400-004 is returned as HTTP 413 by the
body-size middleware) are noted explicitly in the row. Codes never change
once published; if an error condition is removed, the code is retired (its
description is amended to "retired in version X.Y.Z, do not re-use")
rather than reassigned.

| Code | HTTP | type_suffix | Title | Severity | When it occurs | Remediation |
| --- | --- | --- | --- | --- | --- | --- |
| SBS-400-001 | 400 | `SBS-400-001` | Malformed JSON body | Recoverable | The request body cannot be parsed as JSON. | Send a syntactically valid JSON document. Verify with `python -m json.tool` or equivalent. |
| SBS-400-002 | 400 | `SBS-400-002` | Missing required header | Recoverable | A required HTTP header (Idempotency-Key, Content-Type) is absent. | Include the named header on every request. |
| SBS-400-003 | 400 | `SBS-400-003` | Unsupported media type | Recoverable | The request `Content-Type` is not the media type the endpoint accepts. | Set the correct `Content-Type` (`application/json` for most endpoints; `application/x-www-form-urlencoded` for `/v1/oauth/token`). |
| SBS-400-004 | **413** | `REQUEST_BODY_TOO_LARGE` | Request body too large | Recoverable | The request body exceeds the server's configured maximum (default 256 KiB). The HTTP status is 413 even though the code prefix is `SBS-400-`; the prefix is retained for back-compat with the Prompt 5 catalog. | Reduce body size; split large submissions across multiple requests, or use the Tier 2 batch endpoint. |
| SBS-400-005 | 400 | `CURSOR_INVALID` | Cursor invalid | Recoverable | The `next_cursor` value was rejected — either malformed base64, structurally invalid JSON inside, or a tampered HMAC signature (cursors are HMAC-signed per ADR 0028 §cursor-signing). | Treat `next_cursor` as opaque. Pass back the value the server returned verbatim; do not modify it. Restart pagination without a cursor if recovery fails. |
| SBS-400-010 | 400 | `INVALID_SCOPE` | OAuth invalid_scope | Recoverable | Requested scope is unknown, or the intersection of requested and institution-permitted scopes is empty. Returned by `POST /v1/oauth/token` per RFC 6749 §5.2. | Request only scopes from the canonical set (`complaints:write`, `complaints:read`, `batch:upload`, `status:read`); confirm with SBS which scopes your institution is permitted. |
| SBS-400-011 | 400 | `INVALID_REQUEST` | OAuth invalid_request | Recoverable | The token-endpoint request is malformed: unsupported `grant_type`, missing Authorization header, or non-Basic auth scheme. Returned by `POST /v1/oauth/token` per RFC 6749 §5.2. | Send `grant_type=client_credentials` as form-encoded body with `Authorization: Basic <base64(client_id:client_secret)>`. |
| SBS-401-001 | 401 | `CERT_REQUIRED` | Client certificate required | Critical | No mTLS client certificate was presented (direct mode) or no XFCC header was forwarded (proxy mode). | Configure your TLS client to present the certificate SBS issued; verify the corporate-proxy path forwards `X-Forwarded-Client-Cert`. |
| SBS-401-002 | 401 | `CERT_INVALID` | Client certificate invalid | Critical | The certificate failed chain or signature validation, or the XFCC header is missing the `Hash=` or `Subject=` fields, or `notBefore` is in the future. | Re-enroll with SBS to obtain a current certificate; confirm the proxy is configured to forward XFCC in the Envoy-canonical format. |
| SBS-401-003 | 401 | `CERT_EXPIRED` | Client certificate expired | Critical | The presented certificate's `notAfter` is in the past. | Rotate to the renewed certificate SBS issued before the prior one expired. |
| SBS-401-010 | 401 | `SIGNATURE_MISSING_HEADER` | HMAC signature header missing | Recoverable | `X-SBS-Timestamp`, `X-SBS-Signature`, or `X-SBS-Institution-Id` was not present on a request that requires HMAC signing. | Sign the request per ADR 0027 §HMAC canonical request and send all three headers. |
| SBS-401-011 | 401 | `SIGNATURE_ALGORITHM_UNSUPPORTED` | HMAC algorithm unsupported | Recoverable | The `X-SBS-Signature` algorithm prefix is not `hmac-sha256-v1=`. | Use the documented `hmac-sha256-v1=<base64>` form. |
| SBS-401-012 | 401 | `SIGNATURE_INVALID` | HMAC signature invalid | Critical | The signature does not match the canonical request computed by the server (wrong secret, wrong canonical bytes, or tampered body). | Re-compute the signature using the documented six-line canonical request form; confirm the secret matches `active_secret` for your institution. |
| SBS-401-013 | 401 | `SIGNATURE_EXPIRED` | HMAC signature timestamp out of window | Recoverable | The `X-SBS-Timestamp` is more than 5 minutes in the past or more than 60 seconds in the future. | Synchronise your client clock to a reliable NTP source. |
| SBS-401-014 | 401 | `SIGNATURE_REPLAYED` | HMAC signature already seen | Critical | The same signature was observed within the 10-minute replay window (Redis-backed). | Sign each request with a fresh timestamp; do not retry with a captured signature. |
| SBS-401-015 | 401 | `SIGNATURE_INSTITUTION_MISMATCH` | HMAC institution_id does not match mTLS subject | Critical | The `X-SBS-Institution-Id` header value differs from the institution resolved from the mTLS cert. | Send the institution_id that matches the cert presented; do not impersonate another institution. |
| SBS-401-020 | 401 | `TOKEN_REQUIRED` | OAuth access token required | Recoverable | No `Authorization: Bearer <jwt>` header on a protected endpoint. | Obtain an access token from `POST /v1/oauth/token`; include `Authorization: Bearer <token>`. |
| SBS-401-021 | 401 | `TOKEN_INVALID` | OAuth access token invalid | Critical | The JWT signature, issuer, audience, or required-claim validation failed. | Re-fetch the token; verify your client did not mutate the JWT. |
| SBS-401-022 | 401 | `TOKEN_EXPIRED` | OAuth access token expired | Recoverable | The token's `exp` claim is in the past (tokens are valid 15 minutes). | Fetch a fresh token from `POST /v1/oauth/token`. |
| SBS-401-023 | 401 | `TOKEN_CERT_THUMBPRINT_MISMATCH` | OAuth token cert thumbprint mismatch | Critical | The token's `cnf.x5t#S256` claim does not match the SHA-256 thumbprint of the presenting cert (RFC 8705 §3.1 binding). | Use the access token only over the cert it was issued for; rotate both together. |
| SBS-401-024 | 401 | `TOKEN_CERT_REQUIRED` | OAuth token request requires mTLS | Critical | `POST /v1/oauth/token` was reached without a valid mTLS connection. | Present the institution's mTLS certificate when requesting a token. |
| SBS-401-025 | 401 | `INVALID_GRANT` | OAuth invalid_grant | Critical | `client_id` is unknown, `client_secret` is wrong, or the client does not belong to the mTLS-presenting institution. Returned by `POST /v1/oauth/token` per RFC 6749 §5.2. | Confirm `client_id`/`client_secret` from SBS onboarding; verify they were issued for the cert you are presenting. |
| SBS-403-001 | 403 | `CERT_CN_UNKNOWN` | Client certificate CN not registered | Critical | The certificate validated but the `(CN, thumbprint)` is not in `institution_certificates`. | Confirm the institution is onboarded; check whether a cert rotation moved the thumbprint outside the registry. |
| SBS-403-002 | 403 | `CERT_REVOKED` | Client certificate revoked | Critical | The certificate is in the revocation list. | Contact SBS onboarding to confirm; if reissue is appropriate, request a fresh certificate. |
| SBS-403-010 | 403 | `TOKEN_SCOPE_INSUFFICIENT` | OAuth token scope insufficient | Recoverable | The access token does not carry the scope required by this endpoint (e.g. `complaints:write` on `POST /v1/complaints`). | Request a token with the required scope; confirm the scope is in the institution's `permitted_scopes`. |
| SBS-404-001 | 404 | `SBS-404-001` | Resource not found | Informational | The resource_id does not exist or is not visible to the caller. Used for complaints and per-tenant 404 masking (see ADR 0028 §tenant-binding). | Verify the resource id; confirm the caller has access to this tenant. |
| SBS-404-003 | 404 | `SBS-404-003` | Institution not found | Informational | The institution_id does not exist in `institutions`. | Verify the institution_id against SBS's published list. |
| SBS-409-001 | 409 | `SBS-409-001` | Duplicate complaint_id | Recoverable | A complaint with the same complaint_id already exists for this institution. | Use a fresh complaint_id; if intentional re-submission, use idempotency replay (same Idempotency-Key as the original request). |
| SBS-409-002 | 409 | `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_BODY` | Idempotency-Key reused with different body | Recoverable | The Idempotency-Key was reused within the 24-hour window but the request body hash differs from the original. | Use a new Idempotency-Key for the new request, or replay the original body verbatim. |
| SBS-409-003 | 409 | `IDEMPOTENCY_KEY_IN_FLIGHT` | Idempotency-Key in flight | Recoverable | A concurrent duplicate POST hit the same Idempotency-Key while the first request is still processing. Returned after a 150ms wait for the first to complete (ADR 0029 §concurrent-duplicate-POST). | Retry after 1 second (the response carries `Retry-After: 1`); the original request will have completed by then. |
| SBS-412-001 | 412 | `ETAG_MISMATCH` | ETag mismatch | Recoverable | The `If-Match` header carried an ETag that no longer matches the current resource version. | Re-fetch the resource, compare fields you intended to change, and resubmit `PATCH` with the fresh ETag. |
| SBS-422-001 | 422 | `SBS-422-001` | Field validation failed | Recoverable | One or more body fields failed schema validation. The `errors` array enumerates each field-level violation. | Correct each field listed in `errors[].field`; re-submit with a fresh Idempotency-Key. |
| SBS-422-004 | 422 | `RESOLUTION_STATUS_TRANSITION_FORBIDDEN` | Resolution status transition forbidden | Recoverable | A `PATCH /complaints/{id}/status` request requested a transition the state machine does not permit. Permitted transitions are documented in ADR 0028 §9. | Inspect the current `resolution_status` via `GET /complaints/{id}` and submit a permitted transition. |
| SBS-428-001 | 428 | `SBS-428-001` | Precondition required | Recoverable | A conditional `PATCH` arrived without an `If-Match` header (RFC 6585). | Fetch the resource, capture its `ETag`, and replay the `PATCH` with `If-Match: <etag>`. |
| SBS-429-001 | 429 | `RATE_LIMIT_EXCEEDED` | Rate limit exceeded | Recoverable | The institution exceeded its per-minute rate limit. Tier defaults are 1000/min (large) and 100/min (small) per ADR 0033; per-institution overrides are documented in the institutions table. The 429 response carries `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`. | Honour `Retry-After`. Apply client-side pacing using the four headers (present on every authenticated response, not just 429). |
| SBS-429-002 | 429 | `TOKEN_ENDPOINT_RATE_LIMIT_EXCEEDED` | OAuth token endpoint rate limit exceeded | Critical | `POST /v1/oauth/token` exceeded 50 requests/minute keyed on the mTLS CN. This bucket is independent of the business rate limit and protects against `client_secret` brute-force. | Pace token requests; tokens are valid 15 minutes — most clients should hit this endpoint at most a few times per hour. |
| SBS-500-001 | 500 | `SBS-500-001` | Internal server error | Critical | An unexpected error occurred. The response body is intentionally empty (no internal information leak); the `trace_id` field is the support-handoff identifier. | Retry with exponential backoff. If the error persists, contact SBS support with the `trace_id` from the response. |
| SBS-503-001 | 503 | `SBS-503-001` | Service degraded or down | Recoverable | A required dependency (database, Redis, event bus) is unreachable. | Retry with exponential backoff. Monitor https://status-sandbox.sbs.gob.pe (illustrative URL). |
| SBS-503-002 | 503 | `AUTH_NOT_CONFIGURED` | Authentication not configured | Critical | The legacy fail-closed tenancy stub returned this when `AUTH_STUB_ENABLED=false`. After workstream F.7 (Prompt 7) the protected routes use the real mTLS+OAuth chain and this code is retained for back-compat with any unmigrated path; new requests on protected routes now return `SBS-401-001 CERT_REQUIRED` when the mTLS layer rejects them. | Confirm the build has mTLS, HMAC, and OAuth wired (Prompt 7+); for local-only paths that still consult the stub, set `AUTH_STUB_ENABLED=true`. |
| SBS-503-003 | 503 | `HMAC_SECRET_NOT_CONFIGURED` | HMAC secret not configured | Critical | The HMAC verification dependency could not load an `institution_secrets` row for the institution resolved from the mTLS cert — onboarding is incomplete. | Contact SBS onboarding to provision the institution's HMAC secret. |

## Severity classifications

- **Critical** — institution must investigate before retrying; retrying without remediation will reliably fail or produce a security incident.
- **Recoverable** — institution should fix the request and re-submit; retry-with-correction is the normal recovery path.
- **Informational** — the response is acting as documentation (e.g., "complaint not found"); no remediation is needed if the absence is expected.

## Stability commitment

Once a code is published in a tagged release of the OpenAPI specification,
its meaning is frozen for the life of the major version. Description text
may be refined for clarity; the semantics (when the error occurs, the
behaviour to recover) do not change. Retired codes remain documented but
are never re-used.

The versioning policy that governs this stability commitment is defined in
ADR 0013 (Standards Pack distribution) — currently Proposed, target Part 11.

## Retired codes

The following codes were present in the Prompt 5 catalog as placeholders
with explicit "naming needs SBS confirmation" notes. They were superseded
by specific codes in workstream A/B/C/E (Prompt 7) before any external
contract relied on them. They are retired (never re-used).

- **SBS-401-004** (placeholder "Replay attack detected") — replaced by
  `SBS-401-013 SIGNATURE_EXPIRED` (timestamp-window failure) and
  `SBS-401-014 SIGNATURE_REPLAYED` (Redis-cache hit).
- **SBS-401-005** (placeholder "mTLS certificate not trusted") — split into
  `SBS-401-002 CERT_INVALID` (chain/signature/parse failure) and
  `SBS-403-002 CERT_REVOKED` (revocation list hit).
- **SBS-404-002** (placeholder "Batch not found") — folded into the
  generic `SBS-404-001` 404 path.
- **SBS-409-004** (placeholder "Batch not yet completed") — Prompt 8 will
  reintroduce when per-row batch processing lands; not yet returned.
- **SBS-422-002** (placeholder "Cross-field rule failed") — folded into
  `SBS-422-001` field-level errors via the `errors[].rule` discriminator.
- **SBS-422-003** (placeholder "Batch SHA-256 mismatch") — Prompt 8 will
  reintroduce when batch upload verification lands.
