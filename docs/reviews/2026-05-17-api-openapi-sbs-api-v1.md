# Cross-model review — api-openapi-sbs-api-v1

- **Date:** 2026-05-17
- **Model:** gpt-5.4
- **Target:** api-openapi-sbs-api-v1

---

## Summary

The file is readable and mostly consistent. The main strengths are:

- clear separation of Tier 1 and Tier 2
- use of OpenAPI 3.1 with JSON Schema conditionals
- explicit problem response model
- trace context and idempotency called out early
- schemas mostly set to `additionalProperties: false`

I did find several contract issues that are likely to cause implementation drift, client confusion, or security mistakes.

The highest-value findings are:

1. **The top-level security requirement is effectively “AND all three schemes”, not “one of” or “some combination”.** In OpenAPI, one security requirement object means all listed schemes are required. Here that means every secured endpoint requires mTLS **and** OAuth2 **and** HMAC (`api/openapi/sbs-api-v1.yaml`, `security:` near top of file). That may be intended, but the required OAuth scopes do not match the operations, so in practice the contract is internally inconsistent.

2. **Read endpoints require the wrong OAuth scope.** The global security block only names `complaints.write`. Endpoints such as `GET /complaints`, `GET /complaints/{complaint_id}`, `GET /batches/{batch_id}`, and `GET /batches/{batch_id}/results` never override it with read scopes (`complaints.read`, `batches.read`) even though those scopes are defined under `components.securitySchemes.oauth2_client_credentials.flows.clientCredentials.scopes`. This is a contract bug, not a documentation preference.

3. **Institution identity is accepted in request bodies and query params without a clear server-side binding rule.** `Complaint.institution_id`, `BatchManifest.institution_id`, and `GET /complaints?institution_id=...` allow callers to state or filter by institution, but the spec only says identity comes from client cert/token at the edge. There is no explicit rule that the server must ignore or reject mismatches between authenticated institution and payload institution (`Complaint`, `BatchManifest`, and `/complaints` query params). That is a tenant-isolation risk.

4. **Problem responses are underspecified against RFC 9457 and operational support needs.** `ProblemDetail` does not require `detail`, `instance`, `trace_id`, or `errors`; that is acceptable structurally, but there is no statement of when each appears, no response header carrying the trace identifier, and no standard problem types namespace beyond placeholder text. For regulator-grade support and audit, this needs to be tighter.

5. **The contract does not specify critical response headers that clients need to operate safely.** Examples:
   - `traceparent` is said to be returned if absent, but no operations define it as a response header.
   - rate-limited endpoints define `Retry-After` only on 429 responses; there is no `X-RateLimit-*` style contract or equivalent.
   - idempotent create/update endpoints do not indicate whether a response was replayed from cache.
   - `Location` on `201` is typed only as `string`, not `format: uri`.

6. **Several business rules are described in prose but not encoded in schema or parameters.**
   - `/complaints` says cursor-based pagination, but there is no sort order guarantee.
   - `/batches` says there is a webhook callback configured per institution, but no callback contract.
   - `BatchManifest` allows invalid reporting periods because `reporting_period_end >= reporting_period_start` is not encoded.
   - `BatchStatus` count fields are not constrained to reconcile.

7. **There is at least one likely field-definition mistake.** `complainant_district` says “INEI ubigeo at department+province precision” but the pattern is `^\d{4}$`, which is 4 digits, while standard Peru ubigeo codes are commonly handled as 6 digits for department+province+district, and 4 digits is not a usual interchange standard. If 4 digits is intentional, the description should say exactly what coding system is being used. As written it is likely to be misimplemented.

## Disagreements with primary review

I do not have the primary review text, so I cannot directly compare line by line. I can state where I would push back if those points were treated as acceptable.

1. **I would not treat the security model as “good enough for a draft”.**
   The top-level `security` block and scope mismatch are contract-level defects, not polish items. Tooling, generated clients, gateways, and conformance tests will all consume this literally.

2. **I would not accept “implementation details land later” for identity binding and request signing.**
   The file repeatedly defers to “Prompt 7” for mTLS, OAuth, and HMAC details. That is too much deferral for the canonical contract when the same file claims in `info.description` that this specification, not the implementation, is the canonical contract. At minimum the contract needs:
   - canonical signed components
   - timestamp skew window
   - replay window
   - institution identity binding rules
   - precedence when token identity and body `institution_id` disagree

3. **I would not accept placeholders on URLs and namespaces without a marked non-production profile.**
   The sandbox server and token URL are labeled placeholders, and the problem `type` namespace is pending confirmation. For a draft that is fine, but then the contract should make clear that these values are non-normative. Otherwise generated SDKs and downstream docs will bake in placeholders.

4. **I would not count the error model as complete just because RFC 9457 is referenced.**
   The schema shape is there, but the operating rules are not. Regulators and supervised institutions need predictable failure handling. Stripe, GitHub, and Zalando API guidelines all go further here by standardizing correlation identifiers, error codes, and field-error semantics.

## Risks not flagged elsewhere

1. **Cross-tenant read exposure on list and status endpoints**
   - `GET /complaints` exposes `institution_id` as a free filter.
   - `GET /institutions/{institution_id}/status` allows arbitrary institution IDs.
   - `GET /batches/{batch_id}` and `/batches/{batch_id}/results` do not say whether ownership is checked before existence.

   If the implementation returns `404` vs `403` differently by tenant, institutions can enumerate other institutions’ IDs or batch IDs. Industry practice in multi-tenant APIs is to scope lookup by authenticated tenant first and return a generic not-found when outside scope. This is common in AWS control-plane APIs and GitHub repository access patterns.

2. **Request signing scheme is too vague to be interoperable**
   - `components.securitySchemes.hmac_signature` says the signature covers method, path, body hash, timestamp, idempotency key.
   - There is no timestamp header defined.
   - There is no canonicalization rule for path normalization, query ordering, header casing, body encoding, or content-type handling.

   Different clients will sign differently. That causes false authentication failures and hard-to-debug support cases. AWS SigV4 and OCI request signing are the usual comparators: both are extremely specific because vague HMAC specs fail in production.

3. **No anti-replay statement for signed GET requests**
   The HMAC description mentions timestamp and idempotency key, but idempotency applies only to POST/PATCH. GET endpoints still appear to require HMAC through the global security block. Without a defined timestamp header and allowed clock skew, replay protection is unclear.

4. **`traceparent` use is incomplete for observability**
   - Request header exists.
   - Description says server returns one if absent.
   - No response header is defined anywhere.
   - No problem response explicitly includes returned trace context.

   This weakens issue investigation. W3C Trace Context practice is to propagate `traceparent` consistently in responses when promised.

5. **The PATCH response shape is misleading**
   `PATCH /complaints/{complaint_id}/status` returns `ComplaintCreated`. That name and required fields imply a creation receipt, not a state transition result. This will confuse generated SDKs and client code. A dedicated `ComplaintStatusUpdated` or full `Complaint` response would be clearer.

6. **Lack of explicit immutability rules**
   The spec allows complaint retrieval and status patching but says nothing about whether other complaint fields are immutable after creation, whether `complaint_id` is immutable, or whether `resolution_status` can move backward. Some of this is hinted in prose (“illegal status transition”) but not codified. This is audit-sensitive.

7. **No sort order guarantee for cursor pagination**
   `/complaints` and `/batches/{batch_id}/results` use `next_cursor`, but there is no guarantee of stable ordering. Cursor pagination without a deterministic sort key can skip or duplicate items under concurrent writes. Industry practice is to state the sort explicitly, for example `(received_at, complaint_id)` ascending or descending.

8. **Batch upload workflow is incomplete at the contract edge**
   `/batches` returns a presigned `upload_url`, but the contract does not say:
   - expected HTTP method at the upload URL beyond prose
   - required content type
   - maximum file size
   - whether checksum must also be sent to object storage
   - what marks upload completion
   - whether multiple uploads to same URL are allowed

   S3 pre-signed PUT flows and GCS signed URLs usually document these points because client behavior depends on them.

9. **Potential misuse of institution-assigned `complaint_id` as the primary path identifier**
   `Complaint.complaint_id` is described as institution-assigned and used as the unique path key. If uniqueness is only within institution, then path access without tenant scoping is unsafe. If uniqueness is global, the spec should say so. Right now the conflict description says “duplicate complaint_id” but not duplicate within what namespace.

10. **Date/time semantics are not explicit enough**
    - `received_date` is a date only; no timezone issue there.
    - `received_at`, `submitted_at`, `completed_at` are date-times but only one field explicitly says UTC (`ComplaintCreated.received_at`).
    - Other date-time fields should state UTC or offset handling consistently.

11. **No deprecation/versioning policy at operation or schema level**
    The spec has `/version` and a file version, but no compatibility rules:
    - how long older schema versions remain accepted for batch uploads
    - whether new enum values are additive and non-breaking
    - whether clients must tolerate unknown fields in future versions even though current schemas use `additionalProperties: false`

    This matters because regulated institutions change slowly.

12. **OpenAPI examples may train clients into invalid assumptions**
    - `Complaint.examples` and `ValidComplaintSubmission` include `institution_id` in the body. If the server actually derives institution from auth, clients will assume they can set it.
    - The examples never show a problem response, rate-limit response, or idempotency replay response.

## Recommended actions

1. **Fix operation-level security explicitly**
   Replace the global one-size-fits-all security with per-operation requirements, or keep a global baseline and override read endpoints. At minimum:
   - POST `/complaints`: mTLS + OAuth `complaints.write` + HMAC
   - GET `/complaints`, GET `/complaints/{complaint_id}`: mTLS + OAuth `complaints.read` + HMAC if truly required
   - PATCH `/complaints/{complaint_id}/status`: mTLS + OAuth `complaints.write` + HMAC
   - POST `/batches`: mTLS + OAuth `batches.write` + HMAC
   - GET `/batches/{batch_id}`, `/results`: mTLS + OAuth `batches.read` + HMAC if truly required
   - institution status: decide whether `complaints.read`, a separate `institution.status.read`, or supervisor-only access is intended

2. **Write down the tenant-binding rule in the contract**
   Add normative text such as:
   - for institution-authenticated callers, `institution_id` in body or path must match the authenticated institution or the server returns `403`/`422`
   - or better, remove `institution_id` from create bodies and derive it from auth
   - for supervisor callers, define the special authorization path separately

   For this file, I would strongly consider removing `institution_id` from `ComplaintSubmission.complaint` and `BatchManifest` unless there is a clear regulator use case for sending it.

3. **Define the HMAC contract fully**
   Add concrete headers and canonicalization rules:
   - `X-SBS-Timestamp`
   - optional `X-SBS-Key-Id` if needed
   - exact canonical request string format
   - query parameter normalization
   - content hash algorithm and encoding
   - allowed clock skew
   - replay window
   - expected failure codes for signature mismatch vs expired timestamp vs replay detected

   If this detail is not ready, remove HMAC from the canonical contract until it is ready. A half-defined signing scheme is worse than none.

4. **Make observability contractual, not implied**
   Add a reusable response header component for `traceparent` and attach it to all operations, including problem responses. If `trace_id` is used in `ProblemDetail`, define format and relationship to `traceparent`. A simple approach:
   - response header `traceparent`
   - `ProblemDetail.trace_id` = trace-id portion of the W3C trace context

5. **Correct response models**
   - Replace `ComplaintCreated` as the PATCH response with either:
     - full `Complaint`, or
     - new `ComplaintStatusUpdated` with prior status, new status, updated_at, reason
   - Add `format: uri` to `201 Location`
   - Consider `ETag` on `GET /complaints/{complaint_id}` and `If-Match` on PATCH if concurrent status updates are possible

6. **Tighten batch workflow**
   Add at least:
   - `reporting_period_end` must be on or after `reporting_period_start`
   - `row_count_accepted + row_count_rejected <= row_count_submitted`
   - what causes status transitions
   - whether `getBatchResults` is available for `completed_with_errors` only or both completed states
   - explicit upload method and object constraints in the response or schema

7. **Clarify identifier namespaces**
   State whether `complaint_id` is:
   - globally unique across all institutions, or
   - unique only within an institution

   If only within institution, path lookups should be tenant-scoped by auth and conflict text should say “duplicate complaint_id within institution”.

8. **Fix the ubigeo/district field**
   Review `complainant_district` at its schema definition. If the intent is district code, standard Peru ubigeo is usually 6 digits. If the intent is department+province only, the field name should not say district. Pick one and align:
   - name
   - description
   - pattern
   - examples

9. **Add missing operational headers and examples**
   Add reusable components for:
   - `traceparent` response header
   - `Retry-After` with RFC-consistent semantics
   - optional `Idempotency-Replayed: true`
   - maybe `Location` and rate-limit headers

   Also add examples for:
   - 422 field validation failure
   - 409 idempotency mismatch
   - 429 throttling
   - batch row rejection with `problem.errors`

10. **State pagination order**
    For each cursor-based endpoint, define the stable sort key and whether cursors expire. Example:
    - `/complaints`: descending by `received_at`, then `complaint_id`
    - `/batches/{batch_id}/results`: ascending by `row_index`

11. **Normalize date-time language**
    Add “RFC 3339 timestamp in UTC” consistently to all date-time fields: `submitted_at`, `upload_expires_at`, `completed_at`, `last_submission_at`, `checked_at`.

12. **Mark placeholders as non-normative or replace them**
    For `servers`, token URL, and problem type namespace, either:
    - replace with confirmed values, or
    - mark them as illustrative/non-normative in a clear extension field or description

## Triage

_TODO: human-filled. Disposition each finding above as accept / defer / reject, with reason._

---

## Triage (filled 2026-05-18)

| Finding | Disposition | Notes |
| --- | --- | --- |
| 1. Top-level security AND semantics with wrong scope | **ACCEPT — fixed in PR** | Global default changed to `complaints.read`; write ops override. |
| 2. Read endpoints wrong OAuth scope | **ACCEPT — fixed in PR** | Same fix as above. |
| 3. Institution identity binding rule | **DEFER to Prompt 6** | Route-handler rule; lands with FastAPI. Flagged in open-questions §5. |
| 4. ProblemDetail underspecified | **DEFER to Prompt 9** | Extension member policy in error-catalog completion. |
| 5. Missing operational headers | **DEFER to Prompt 6** | `traceparent` response header, `Idempotency-Replayed` deferred; `Location: format: uri` accepted now. |
| 6. Prose-only business rules | **PARTIAL ACCEPT** | `Location` typing fixed in PR; period-end >= period-start and count reconciliation deferred to Prompt 8. |
| 7. ubigeo length mistake | **ACCEPT — fixed in PR** | Changed from `^\d{4}$` to `^\d{6}$`; canonical INEI DDPPDD. |
| Risk 1 — cross-tenant read exposure | **DEFER to Prompt 6** | Server-side tenant-scoping rule lands with FastAPI handlers. |
| Risk 2 — HMAC canonicalisation vague | **DEFER to Prompt 7** | Full signing contract lands with security primitives. ADR 0027 amendment in Prompt 6. |
| Risk 3 — no anti-replay for GETs | **DEFER to Prompt 7** | Same. |
| Risk 4 — traceparent observability | **DEFER to Prompt 6** | Response-header component. |
| Risk 5 — PATCH response misleading | **ACCEPT — fixed in PR** | Returns `Complaint`, not `ComplaintCreated`. |
| Risk 6 — immutability rules | **DEFER to SBS review** | Policy decision. |
| Risk 7 — pagination sort order | **DEFER to Prompt 9** | Portal docs polish. |
| Risk 8 — batch upload workflow | **DEFER to Prompt 8** | Tier 2 pipeline work. |
| Risk 9 — complaint_id namespace | **DEFER to Prompt 6** | One-line description clarification when route handler lands. |
| Risk 10 — date-time UTC language | **DEFER to Prompt 9** | Wording polish. |
| Risk 11 — deprecation policy | **DEFER to ADR 0013 / Part 11** | Standards Pack distribution. |
| Risk 12 — examples misleading clients | **DEFER to Prompt 6** | Tied to institution-binding rule. |
