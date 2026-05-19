# ADR 0029 — Idempotency-Key policy

- **Status:** Accepted
- **Date:** 2026-05-18
- **Target prompt / Part:** Prompt 6 / Part 2
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

The institution-facing API accepts unsafe operations (POST, PATCH) under
at-least-once delivery semantics. A delivery library that times out on a
slow network and retries must not create duplicate complaints. The
OpenAPI spec declares `Idempotency-Key` as a required header on POST
`/v1/complaints` and POST `/v1/batches`, and supports it on PATCH
`/v1/complaints/{id}/status`. Prompt 6 needs to lock the storage shape,
the replay-match policy, the body-hash mismatch policy, the TTL, and the
interaction with the ETag-based concurrency control on PATCH.

## Decision

**Storage shape.** The `idempotency_records` table carries
`(record_id, institution_id, idempotency_key, body_sha256,
response_status, response_payload, response_headers, request_method,
request_path, created_at, expires_at)`. A unique index over
`(institution_id, idempotency_key)` enforces per-tenant scope. Records
live for 24 hours from creation.

**Replay-match.** On a request with an `Idempotency-Key`, the server
hashes the raw request body (SHA-256, full 32 bytes) and looks up the
record by `(institution_id, idempotency_key)`.

- No record found → process the request normally, persist the result
  before returning.
- Record found, hash matches, not expired → return the cached
  `response_status`, `response_payload`, and `response_headers`, plus an
  added header `Idempotency-Replayed: true`.
- Record found, hash differs, not expired → 409 with stable code
  `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_BODY`. The client used the same
  key for a different request, which is a client bug.
- Record found, expired → process the request normally (the record is
  not surfaced to the client; the sweep job in Prompt 7 will remove it).

**TTL.** 24 hours. Long enough to cover any retry policy a reasonable
client library implements; short enough that the table stays small. The
sweep job that prunes expired records lands in Prompt 7 alongside the
rate limiter (they share a scheduler).

**Interaction with ETag (PATCH).** ETag is the *concurrency* control
(if the resource changed under you, your PATCH must be re-evaluated);
Idempotency-Key is the *retry* control (if your delivery library
retransmitted, the same outcome must result). A PATCH with matching
ETag + matching Idempotency-Key is naturally idempotent; the
idempotency-key on PATCH is belt-and-suspenders. We support both because
some delivery libraries retry without conditional requests, and Stripe's
reference policy applies Idempotency-Key uniformly across unsafe
methods.

**Header semantics.** `Idempotency-Replayed: true` is part of the public
contract — declared in the OpenAPI spec's response headers for POST
`/v1/complaints` and POST `/v1/batches`. Operators reading access logs
can filter on the header to count duplicate-retry traffic.

## Precedent

Stripe's documented Idempotency-Key policy:
- 24-hour retention window.
- Body hash check on replay.
- 409 on mismatched body with same key.
- Idempotency-Key on every unsafe method.

This is the reference implementation cited across the regulator-domain
literature; UK Open Banking's payment-initiation idempotency policy is
materially identical.

A specific section in
[docs/research/market-comparators.md §5.A](../research/market-comparators.md#5a-api-and-schema-layer)
discusses the at-least-once delivery requirement for the institution-
facing API; cite that section for the property-of-the-domain framing
(institutions are not in our network, network failures are not our
fault, the API must be safe to retry).

## Divergence

We diverge from a minimal "idempotency is the client's problem" stance
that some internal-API references take. The institution-facing audience
includes vendors writing batch-delivery code in COBOL-on-Linux and
Java-on-mainframe contexts where retry libraries are heterogenous; the
server-side guarantee is the right place to draw the line.

We also diverge from a "permissive replay" approach where the cached
response is returned regardless of body hash. That approach is wrong
because a client bug that re-uses a key with a different body is a
correctness issue; surfacing it as 409 lets the institution's
integration team diagnose and fix the bug rather than silently shipping
the wrong response.

## Consequences

- Every POST and PATCH handler reads the raw request body to hash it.
  The body-size-limit middleware caches the body on `request._receive`
  so the second read is in-process and free.
- The `idempotency_records` table grows linearly with 24-hour Tier 1
  traffic. The May 25 sandbox uses an *illustrative* planning figure of
  ~10k Tier 1 submissions per day per institution, against which the
  table would hold under 500 KiB per institution at steady state. Both
  numbers are sandbox planning estimates, not measured values; a
  post-May-25 benchmark will replace them. Either way the sweep job is
  preventive hygiene, not load shedding.
- The `Idempotency-Replayed: true` header lets observability dashboards
  distinguish unique submissions from retried ones. The Tier 1 ingestion
  count is per-unique-submission, not per-request.
- PATCH on a complaint with the same idempotency-key but a mutated
  resource between the original request and the retry is the awkward
  case. The current behavior is: the cached response is returned, which
  may not reflect the current state. The mitigation is the ETag check —
  if the resource changed, the cached If-Match no longer matches and the
  retry returns 412 from the *first* request, which the cache stores.
  Documented in the route handler and in the error-catalog entry for
  `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_BODY`.
- The 24-hour TTL is a configuration knob (`SBS_API_IDEMPOTENCY_TTL_SECONDS`)
  so a regulator-domain reason to extend retention (an audit trail
  requirement, for example) can be applied without a code change.

## Amendments

### 2026-05-19 — concurrent-duplicate-POST policy (Prompt 7)

The original §Decision did not specify behaviour when two requests with
the same `Idempotency-Key` and same body arrive concurrently (e.g., a
delivery library that retries before the first request has finished).
The Prompt 6 closeout flagged this as a carry-forward.

**Amendment.** The `idempotency_records` row gains a `state` column
(`processing | complete`). The handler flow is:

1. The handler attempts an INSERT of a placeholder row with
   `state=processing` and the unique constraint
   `(institution_id, idempotency_key)`. If the INSERT succeeds, this
   request is the *first* in flight; the handler proceeds and updates
   the row to `state=complete` with the response payload once the work
   is done.
2. If the INSERT fails on the unique-constraint, this request is the
   *second* in flight. The handler reads the existing row and:
   - If `state=complete` → return the cached response with
     `Idempotency-Replayed: true` (the existing behaviour).
   - If `state=processing` → wait `50ms × 3` retries, re-reading the
     row each time. If the row reaches `state=complete` within 150ms,
     return the cached response. If it does not, return 409
     `IDEMPOTENCY_KEY_IN_FLIGHT` with `Retry-After: 1`.

The 50ms/3-retry shape is intentionally short. A request that is *still*
in flight after 150ms is more likely stuck than nearly-finished, and the
client's retry will land within a second.

### 2026-05-19 — replay-header safelist (Prompt 7)

The original §Decision said replay returns "the cached
`response_status`, `response_payload`, and `response_headers`." Prompt 6
closeout flagged that some headers must be *recomputed per request*
(the date, the trace context) rather than replayed verbatim; the
distinction needs to be explicit so reviewers can tell which headers
the implementation must filter.

**Amendment.** The safelist is enumerated explicitly. On replay:

- **Replayed verbatim from `response_headers`:** `Content-Type`,
  `Location`, `ETag`, `Idempotency-Replayed`, `X-RateLimit-Limit`.
- **Recomputed for the current request:** `Date`, `Server`,
  `traceparent`, `X-Correlation-Id`, `X-RateLimit-Remaining`,
  `X-RateLimit-Reset`, `Retry-After`.

The implementation lives at `api/sbs_api/idempotency.py` as a constant
named `REPLAY_HEADER_SAFELIST` with a code comment naming each header's
category. New response headers added to a route default to *recomputed*
(safe) unless explicitly added to the safelist; the test
`test_replay_header_safelist.py` enforces this.

The rationale: `Date` and `Server` are HTTP-protocol-level headers that
clients use for cache-staleness reasoning; replaying them would mislead.
`traceparent` and `X-Correlation-Id` are observability handoff keys for
the *current* request, not the original. `X-RateLimit-Remaining` and
`X-RateLimit-Reset` reflect the *current* bucket state; replaying them
would mislead the client's pacing logic. `X-RateLimit-Limit` is replayed
because the limit value does not change between the original and the
replay (unless the operator changed the tier, which is rare).
