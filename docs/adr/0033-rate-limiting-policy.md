# ADR 0033 — Rate limiting policy and tiers

- **Status:** Accepted
- **Date:** 2026-05-19
- **Target prompt / Part:** Prompt 7 / Part 3
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

The institutional integration profile spans two orders of magnitude:
large banks running Tier 1 ingestion at sustained near-real-time rates,
and small COOPACs sending tens to hundreds of complaints per day during
working hours. A single rate limit serves neither well — too low chokes
the banks, too high gives a misbehaving small institution nine orders of
magnitude of room to misbehave before the limit fires.

The Supervisor's proportional-treatment framing for SBS supervised institutions
is the conceptual anchor: small institutions are not held to large-bank
standards on integration sophistication, and large banks are not capped
to small-COOPAC traffic ceilings. The rate limit must reflect that.

A Redis-backed token bucket gives per-institution accounting that is
both atomic and cheap. The atomicity comes from a Lua script; the cost
is one Redis round-trip per request. The bucket fills continuously at
`tier_per_minute / 60` per second, capping at `tier_per_minute`.

This ADR locks the policy and tiers. The operational details (Lua
script, key shape, header semantics) are implementation, but the
*contract* — what an institution sees as a 429 — is part of the public
contract surface and is included here.

## Decision

**Two tiers.** Each institution is classified `large` or `small` on the
`institutions.tier_classification` column. Defaults:

| Tier | Default limit | Suitable for |
| --- | --- | --- |
| `large` | 1000 requests/minute | Major banks with Tier 1 integration. |
| `small` | 100 requests/minute | COOPACs, small financieras, sandbox testers. |

**Per-institution override.** `institutions.rate_limit_per_minute`
(nullable). When non-null, overrides the tier default. The override is
the operator's escape hatch for an institution whose traffic profile
deviates from its tier (e.g., a midsize bank in the small tier that
needs 500/min during reconciliation windows).

**Token bucket on Redis, Lua-scripted.** A single Redis Lua script
performs the atomic decrement-and-fetch:

```lua
-- KEYS[1] = bucket key (sbs:rate:<institution_id>)
-- ARGV[1] = current time (unix ms)
-- ARGV[2] = limit (requests/minute)
-- ARGV[3] = window (ms)
-- Returns: { remaining, reset_unix_ms, retry_after_seconds }
```

The script is the *only* mutation path for the bucket; this is what
guarantees concurrent requests do not double-count.

**Middleware placement.** The rate-limit middleware runs *inside* the
OAuth token validation (the `institution_id` is already resolved at this
point) and *outside* the route handler. It applies to every protected
endpoint; unauthenticated endpoints that *do not* resolve an
institution (health probes, openapi) are bypassed by an explicit
allowlist.

**Token endpoint has its own bucket.** `POST /v1/oauth/token` is *not*
on the allowlist — it has a separate, tighter token-endpoint bucket of
**50 requests/minute per institution** (keyed on the mTLS subject's
CN, since the OAuth token has not yet been issued). Rationale: RFC
6749 §10.10 SHOULD on authorization-server throttling, and Stripe's
token endpoint runs at this scale. The bucket protects against
brute-force `client_secret` enumeration by an attacker who has somehow
acquired a valid mTLS cert. On exhaustion the endpoint returns 429
with stable code `TOKEN_ENDPOINT_RATE_LIMIT_EXCEEDED` and the same
four headers as the business-bucket 429.

**429 response shape.** RFC 9457 problem+json with stable code
`RATE_LIMIT_EXCEEDED`:

```json
{
  "type": "https://sbs.gob.pe/errors/rate-limit-exceeded",
  "title": "Rate limit exceeded",
  "status": 429,
  "code": "RATE_LIMIT_EXCEEDED",
  "detail": "Institution BANCO_DEMO_001 exceeded its limit of 1000 requests/minute. Retry after 12 seconds."
}
```

**Headers on every response.** Four headers are emitted on every
authenticated response (2xx, 4xx, 5xx — not just on 429):

| Header | Value |
| --- | --- |
| `X-RateLimit-Limit` | Effective limit for this institution. |
| `X-RateLimit-Remaining` | Tokens remaining in the bucket. |
| `X-RateLimit-Reset` | Unix timestamp at which the bucket is next full. |
| `Retry-After` | (429 only) Seconds until the next request may succeed. |

## Precedent

[docs/research/market-comparators.md §5.A.M](../research/market-comparators.md#5am-authentication-signing-and-rate-limiting-for-regulator-facing-apis)
cites
[**Stripe's API rate-limiting documentation**](https://stripe.com/docs/rate-limits)
as the single solid precedent for this pattern. Stripe documents
exactly: a per-account token bucket, four response headers (`Retry-After`
plus the three `X-RateLimit-*`), and a `429` with `Retry-After` on burst
overruns. The tier abstraction (large vs small) mirrors the Supervisor's
proportional-treatment framing for SBS supervised institutions; Stripe
itself differentiates "test" and "live" account limits, which is the
same shape applied to a different axis.

## Divergence

We diverge from a *single global limit* (the simplest posture) because
the bank/COOPAC traffic split makes any single limit wrong for at least
one population.

We diverge from a *reverse-proxy-only* posture (limit at NGINX/Envoy,
not in the application) because a proxy limit does not know the
institution: it sees the connection. The proxy will additionally apply a
DoS-protection limit in production; the application-layer limit is the
*business* limit and is the one institutions see.

We diverge from *sliding-window rate limiting* (Stripe's actual
underlying implementation, more precise but heavier) because a token
bucket is cheaper to reason about and the precision difference at our
traffic volumes is not material.

We diverge from *per-endpoint limits* (Stripe applies different limits
to different endpoints) because the institutional integration profile
is overwhelmingly POST `/v1/complaints` — splitting the limit across
endpoints would either under-utilise budget for the dominant endpoint
or invite gaming.

## Consequences

- The Lua script is the single source of correctness. Reviewers focus on
  it; the surrounding Python is a wrapper.
- A production reverse proxy applies its own outer DoS-protection limit
  (e.g., 10x the application limit, per-IP). The two limits are
  intentionally redundant: the proxy protects the application, and the
  application enforces the institutional contract.
- Burst behaviour: a fully-empty bucket recovers to full in 60 seconds.
  An institution that exhausts its bucket cannot burst-recover; it must
  wait. This is by design — a recovered burst capability is what makes
  rate limits useless for protecting downstream systems.
- The `tier_classification` and `rate_limit_per_minute` columns on
  `institutions` are operator-set, not self-service. An institution that
  needs a different tier opens a ticket; SBS operations updates the
  column. The self-service path (an admin endpoint) is a Part 8
  decision.
- `X-RateLimit-*` on every response (not just on 429) gives the
  institution's SDK a continuous signal of remaining capacity. This is
  the Stripe pattern; clients can pace themselves without provoking the
  429.
- Redis is now a hard dependency. The Compose stack (`scripts/dev-up.sh`)
  must bring it up. A test fixture that does not need rate limiting can
  disable the middleware via the same allowlist mechanism, but the
  default test app includes Redis via testcontainers.
- **Batch upload bypasses the request-level limit semantically.** One
  `POST /v1/batches` may carry N complaints, so the effective
  complaint-ingestion rate from a single Tier 1 institution is
  unbounded by the request-per-minute limit alone. Post-May-25
  benchmark will inform whether a separate `batch_per_hour` limit, or
  a compute-units approach per Stripe, is justified. This is recorded
  as a future-amendment trigger, not a blocker for the May 25 sandbox
  (synthetic data only, no production volume).
