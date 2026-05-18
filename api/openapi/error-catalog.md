# SBS SupTech Complaints API — Error Catalog

This catalog is the canonical list of stable error codes returned by the SBS
SupTech Complaints API. Each error code is paired with an RFC 9457 `type`
URI, an HTTP status, a severity classification, the conditions that produce
it, and remediation guidance.

The `type` URI namespace `https://sbs.gob.pe/errors/{code}` is a **placeholder
pending SBS sign-off**. Until confirmed, institutions should treat the
`code` field as the stable identifier and the `type` URI as advisory. See
`docs/sessions/2026-05-18-prompt-05-open-questions.md` §1.1 and §2 for the
status of namespace confirmation.

Error codes follow the pattern `SBS-<http-status>-<sequence>`, where
`<sequence>` is a zero-padded three-digit number unique within the status
class. Codes never change once published; if an error condition is removed,
the code is retired (its description is amended to "retired in version
X.Y.Z, do not re-use") rather than reassigned.

| Code | HTTP | Title | Severity | When it occurs | Remediation |
| --- | --- | --- | --- | --- | --- |
| SBS-400-001 | 400 | Malformed JSON body | Recoverable | The request body cannot be parsed as JSON. | Send a syntactically valid JSON document. Verify with `python -m json.tool` or equivalent. |
| SBS-400-002 | 400 | Missing required header | Recoverable | A required HTTP header (Idempotency-Key, Content-Type) is absent. | Include the named header on every request. |
| SBS-400-003 | 400 | Unsupported media type | Recoverable | The request `Content-Type` is not `application/json`. | Set `Content-Type: application/json` on POST and PATCH requests. |
| SBS-400-004 | 400 | Request body too large | Recoverable | The request body exceeds the server's configured maximum (default 256 KB). Stable code returned as `REQUEST_BODY_TOO_LARGE`. | Reduce body size; split large submissions across multiple requests, or use the Tier 2 batch endpoint. |
| SBS-400-005 | 400 | Cursor invalid | Recoverable | The `next_cursor` value was rejected by server-side validation — either malformed base64, structurally invalid JSON inside, or tampered values that do not match an active page. Stable code `CURSOR_INVALID`. | Treat `next_cursor` as opaque. Pass back the value the server returned verbatim, or restart pagination without a cursor. |
| SBS-401-001 | 401 | Missing authentication | Recoverable | No mTLS client certificate, OAuth bearer token, or HMAC signature was presented. | Configure your client per the developer portal authentication guide. |
| SBS-401-002 | 401 | Invalid OAuth token | Recoverable | The OAuth access token is malformed, expired, or signed by an unknown authority. | Re-fetch the token from the token endpoint with valid client credentials. |
| SBS-401-003 | 401 | Invalid HMAC signature | Recoverable | The HMAC signature does not match the request body and headers. | Re-compute the signature using the documented canonical request form. |
| SBS-401-004 | 401 | Replay attack detected | Critical | The request timestamp is outside the acceptance window (±5 minutes) or the (institution_id, signature) pair was already seen. | Synchronise your client clock to a reliable NTP source and ensure each request carries a unique signature. |
| SBS-401-005 | 401 | mTLS certificate not trusted | Critical | The presented client certificate is not issued by the SBS CA or has been revoked. | Re-enroll with SBS to obtain a current certificate. **(Naming needs SBS confirmation — see open-questions §4.)** |
| SBS-403-001 | 403 | Scope missing | Recoverable | The bearer token does not carry the scope required for this operation. | Request a token with the required scope (e.g., `complaints.write`). |
| SBS-403-002 | 403 | Institution not onboarded | Critical | The institution has not completed sandbox onboarding. | Contact the SBS onboarding team. **(Naming needs SBS confirmation — see open-questions §4.)** |
| SBS-404-001 | 404 | Complaint not found | Informational | The complaint_id does not exist or is not visible to the caller. | Verify the complaint_id; confirm the caller has access scope. |
| SBS-404-002 | 404 | Batch not found | Informational | The batch_id does not exist or is not visible to the caller. | Verify the batch_id from the POST /batches response. |
| SBS-404-003 | 404 | Institution not found | Informational | The institution_id does not exist. | Verify the institution_id against SBS's published list. |
| SBS-409-001 | 409 | Duplicate complaint_id | Recoverable | A complaint with the same complaint_id already exists for this institution. | Use a fresh complaint_id; if intentional re-submission, use the idempotency replay (same Idempotency-Key as the original request). |
| SBS-409-002 | 409 | Idempotency-Key reused with different body | Recoverable | The Idempotency-Key was reused within the 24-hour window but the request body hash differs from the original. Stable code `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_BODY`. | Use a new Idempotency-Key for the new request, or replay the original body verbatim. |
| SBS-409-003 | 409 | Illegal status transition | Recoverable | The requested resolution_status transition is not permitted from the current state. | Inspect the current state via GET /complaints/{complaint_id} and submit a permitted transition. |
| SBS-409-004 | 409 | Batch not yet completed | Informational | Results requested for a batch that is still processing. | Poll GET /batches/{batch_id} until status is `completed` or `completed_with_errors`. |
| SBS-412-001 | 412 | ETag mismatch | Recoverable | The `If-Match` header carried an ETag that no longer matches the current resource version. Stable code `ETAG_MISMATCH`. | Re-fetch the resource, compare fields you intended to change, and resubmit `PATCH` with the fresh ETag. |
| SBS-422-001 | 422 | Field validation failed | Recoverable | One or more body fields failed schema validation. The `errors` array in the problem detail enumerates each field-level violation. | Correct each field listed in `errors[].field`; re-submit with a fresh Idempotency-Key. |
| SBS-422-002 | 422 | Cross-field rule failed | Recoverable | A cross-field constraint failed. In v0.1.0 the enforced rules are: (a) `original_reference_id` must not equal `complaint_id` on a `Complaint` submission, and (b) `reason` (≥10 non-whitespace characters) is required when `ComplaintStatusPatch.resolution_status` is `atendido` or `anulado`. | Read the `detail` message; satisfy the named constraint. |
| SBS-422-003 | 422 | Batch SHA-256 mismatch | Critical | The uploaded batch file's SHA-256 does not match the manifest. | Recompute the hash on the file being uploaded; re-submit a fresh manifest. |
| SBS-422-004 | 422 | Resolution status transition forbidden | Recoverable | A `PATCH /complaints/{id}/status` request requested a transition that the state machine does not permit (for example, `atendido → pendiente` or `anulado → atendido`). Stable code `RESOLUTION_STATUS_TRANSITION_FORBIDDEN`. The permitted transitions and terminal-state rule are documented in ADR 0028 §9. | Inspect the current `resolution_status` via `GET /complaints/{id}` and submit a permitted transition. |
| SBS-428-001 | 428 | Precondition required | Recoverable | A conditional `PATCH` arrived without an `If-Match` header (RFC 6585). | Fetch the resource, capture its `ETag`, and replay the `PATCH` with `If-Match: <etag>`. |
| SBS-429-001 | 429 | Per-institution rate limit exceeded | Recoverable | The institution exceeded its configured per-minute rate limit. | Honour the Retry-After header. Apply client-side rate limiting. |
| SBS-500-001 | 500 | Internal server error | Critical | An unexpected error occurred. | Retry with exponential backoff. If the error persists, contact SBS support with the `trace_id` from the response. |
| SBS-503-001 | 503 | Service degraded or down | Recoverable | A required dependency (database, event bus) is unreachable. | Retry with exponential backoff. Monitor https://status-sandbox.sbs.gob.pe (illustrative URL). |
| SBS-503-002 | 503 | Authentication not configured | Critical | The runtime tenancy-binding dependency is wired to a stub but `AUTH_STUB_ENABLED=False`, so the server fails closed rather than handling traffic with a placeholder identity. Stable code `AUTH_NOT_CONFIGURED`. The real authentication primitives land in Prompt 7. | For local development, set `AUTH_STUB_ENABLED=True`. For staging or production, deploy the build with real authentication wired (Prompt 7+). |

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
