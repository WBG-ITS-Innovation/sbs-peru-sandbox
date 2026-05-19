# ADR 0035 — Outbound webhook signing contract

- **Status:** Accepted
- **Date:** 2026-05-20
- **Target prompt / Part:** Prompt 8 / Part 4
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

When the API needs to tell an institution something — "your batch is
complete", "your batch failed", and in later prompts "an agent has a
finding for you" — it calls back to a URL the institution registered.
That callback travels the public internet (or, in production, a
regulator-mediated path) and reaches a service the institution
operates. The institution needs to verify that the callback actually
came from SBS and was not tampered with in transit.

The inbound contract (ADR 0027 amendment) already covers HMAC signing
for institution-to-SBS requests. The outbound contract needs the
same primitive in the other direction, with the same shape so SDK
authors implement one verification recipe rather than two.

The URL the callback goes to is per-institution and registered
out-of-band. A misconfigured or hostile URL is a server-side request
forgery (SSRF) risk: a webhook delivery to `http://169.254.169.254/`
(the AWS instance metadata service) could exfiltrate IAM credentials
to whoever owns the institution's webhook config row. URL validation
is not optional.

## Decision

When the API calls back to an institution (batch completion, batch
failure, future agent-triggered events), the call is signed with
HMAC SHA-256 using a per-institution **outbound** secret distinct
from the inbound HMAC secret.

**Canonical request shape.** Five lines, same shape as ADR 0027
inbound:

```
<HTTP-method-uppercase>
<callback-path>
<X-SBS-Timestamp-value>
<lowercase-hex(sha256(body))>
<institution_id>
```

The shape mirrors inbound so SDK authors implement one
verify_signature() routine.

**Headers on every callback:**

- `X-SBS-Timestamp: <RFC 3339 UTC>` — same skew tolerance as inbound
  (5 minutes ±300 seconds).
- `X-SBS-Signature: hmac-sha256-v1=<base64>` — same algorithm
  prefix.
- `X-SBS-Key-Id: sandbox-v1` — identifies which secret was used to
  sign. Value is `sandbox-v1` from day one, mirroring the OAuth
  `kid=sandbox-v1` pattern from ADR 0032. Future rotation rolls in a
  new `kid` (e.g., `sandbox-v2`); the previous secret stays valid in
  the `active` slot until cutover, then is moved to `previous` for
  the grace window, then retired. The rotation reader logic itself
  is deferred to Part 8 admin work; the `kid` column on
  `outbound_webhook_secrets` is in place from day one so no migration
  is required when rotation lands.

**Secret storage.** The `outbound_webhook_secrets` table is separate
from `institution_secrets` so inbound and outbound rotate
independently. Each row carries `active_secret`, `previous_secret`,
`previous_secret_retires_at`, and `kid`. Both columns store the
secret in raw bytes for the sandbox; the production overlay wraps
them with the KMS-encrypted column type when the secret store lands
in Part 8.

**Replay protection.** The outbound side does not enforce replay
protection on the receiving institution's behalf. That is the
institution's responsibility per their verification recipe (the SDK
recipe documents the pattern: track recently-seen signatures, reject
duplicates within the skew window). Skipping server-side enforcement
on the outbound side is acceptable because the server is the sender,
not the receiver.

**Retry policy.** Delivery retries with exponential backoff:
30 seconds, 2 minutes, 10 minutes, 1 hour, 6 hours — 5 attempts
total, ~7.7-hour window. Persistent failures recorded in
`webhook_deliveries` with status `delivery_failed`. Default policy
is no auto-disable on persistent failure; the disable/re-enable
admin path lands in Part 8.

**Webhook URL validation.** The callback URL is per-institution and
stored in `institution_webhook_configs`. Before each delivery
attempt the URL is validated against three checks:

1. Scheme must be HTTPS — `http://` is rejected.
2. Host must be FQDN — bare hostnames and IP literals are rejected.
3. Host must resolve to a public IP — RFC 1918 private ranges,
   link-local (169.254/16), loopback (127/8), and the AWS instance
   metadata service IP `169.254.169.254` are rejected.

Validation failure marks the delivery `delivery_failed` with
`code=WEBHOOK_URL_REJECTED` and emits a structlog event; no retry.

**Sandbox override.** The sandbox seeds demo institutions' callback
URLs to the docker-compose `webhook-listener` service, which by
design fails all three checks (non-HTTPS, bare hostname, private
docker-network IP after resolution). A single env var
`SBS_API_ALLOW_INSECURE_WEBHOOK_URLS=true` bypasses all three
validation checks. The name signals the breadth of the override —
an earlier draft used a narrower `ALLOW_PRIVATE_WEBHOOK_URLS` name
which was misleading because the seeded URL also fails the HTTPS
and FQDN checks.

The override is gated to `environment in {test, dev}`. Startup
refuses to boot if `SBS_API_ALLOW_INSECURE_WEBHOOK_URLS=true` is set
with `environment in {staging, prod}`.

**Webhook as convenience, polling as correctness.** The webhook is
the *convenience* layer; `GET /v1/batches/{batch_id}` is the
*correctness* layer. An institution (e.g., a 12-person COOPAC) that
misses the webhook due to a weekend outage recovers by polling the
status endpoint. The 7.7-hour retry window is acceptable on that
basis — it would be too short if the webhook were the only delivery
mechanism, but it isn't. This framing is what makes the retry policy
defensible against the "Stripe retries for 3 days" pushback: Stripe
has no polling fallback, SBS does.

## Precedent

[docs/research/market-comparators.md §5.A.M](../research/market-comparators.md#5am-authentication-signing-and-rate-limiting-for-regulator-facing-apis)
is extended in this prompt for outbound flows. The canonical
reference is **Stripe webhooks**: HMAC signing, timestamp and
signature headers, replay-resistant by timestamp window,
exponential-backoff retry, persistent failure recording. The same
shape is used by GitHub webhooks, Twilio request validation, and
every regulator-domain callback flow the comparator file enumerates.

Stripe's auto-disable-after-extended-failure pattern is documented
but not adopted in the sandbox; the admin-disable surface in Part 8
is the equivalent. Stripe's 3-day retry window is the upper bound;
the SBS sandbox uses 7.7 hours because polling is available as a
fallback, which Stripe does not have.

The SSRF-protection ruleset (HTTPS-only, FQDN, no private/loopback/
link-local) follows the OWASP SSRF prevention cheat sheet and the
Cloud Security Alliance guidance for cloud-hosted webhook senders.
The specific call-out of `169.254.169.254` follows the IMDSv1
exfiltration patterns documented after the 2019 Capital One incident.

## Divergence

We diverge from Stripe's 3-day retry window because Stripe has no
polling fallback. SBS has `GET /v1/batches/{batch_id}` as the
correctness layer; the webhook is convenience. A shorter window is
acceptable here.

We diverge from "let institutions register any URL". The three URL
validation checks block the most common SSRF vectors. SBS analysts
register URLs out-of-band (admin-API in Part 8); the check is
defence-in-depth even though the registration path is supposed to be
trusted.

We diverge from "auto-disable webhooks after N failed deliveries"
(Stripe's pattern). The sandbox keeps the webhook configured even
after persistent failure because the institution may be in a
short-term outage and re-enable would require operational
coordination we have not yet built. The Part 8 admin API adds
explicit disable/re-enable.

We diverge from a separate `event_type` column on
`institution_webhook_configs`. YAGNI — there is one event type today
(batch completion). Reintroduce in Prompt 12 when agent events
actually need event-type routing.

## Consequences

- Institutions must implement signature verification on their
  callback receiver. The verification recipe is documented in
  markdown alongside this prompt; language-specific SDK helpers
  (Python, TypeScript) land in Prompt 9 as part of the developer-
  portal completion.
- Outbound secrets rotate independently of inbound. Rotation
  procedure (with the `kid` column already in place) is operator-
  driven via Part 8 admin-API.
- The 5-attempt retry window is sandbox-shaped; production may
  extend it to match Stripe's 3-day pattern once SBS operations
  confirms what is realistic for institutional uptime profiles.
- The `SBS_API_ALLOW_INSECURE_WEBHOOK_URLS` override is a
  development convenience with a deliberately broad name and a
  startup-time guard against staging/prod. Operators who try to
  ship it to production will be told no at boot.
- Webhook failures show up in structlog as
  `webhook.delivery.attempt` (each attempt) and
  `webhook.delivery.dead_letter` (final failure with full attempt
  history). Part 8 surfaces these in an admin UI; until then,
  operators grep.
