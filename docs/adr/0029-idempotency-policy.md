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
  traffic. At the May 25 sandbox target of ~10k Tier 1 submissions per
  day per institution, the table holds <500 KiB per institution at
  steady state; not a capacity concern. The sweep job is preventive
  hygiene, not load shedding.
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
