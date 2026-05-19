# ADR 0027 — OpenAPI specification as the canonical contract

- **Status:** Accepted
- **Date:** 2026-05-18
- **Target prompt / Part:** Prompt 5 / Part 2
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

FastAPI's default working pattern is *Pydantic-first*: the developer
defines Pydantic models, FastAPI generates the OpenAPI specification from
those models at startup, and the generated specification is served at
`/openapi.json`. The Pydantic models are the source of truth; the OpenAPI
specification is the derived artifact.

This pattern is excellent for Python-only teams shipping ergonomic
internal APIs. It is the wrong default for an institution-facing regulator
API because:

1. The audience that integrates against the API does so in .NET, Java,
   TypeScript, and Python. The OpenAPI specification is what their code
   generators consume; the Pydantic models are not visible to them.
2. A regulator-grade contract must be readable and reviewable as a
   human-curated document. Generated OpenAPI tends to carry artifact
   noise (Pydantic-specific `$ref` shapes, default `additionalProperties`
   inheritance, ordering quirks) that obscures the intent.
3. Contract stability is a regulator-grade requirement. A Pydantic refactor
   that incidentally renames a field, alters a `Literal`, or changes a
   nullable default would silently rewrite the published contract.
   Treating the OpenAPI specification as canonical makes contract changes
   deliberate edits to a YAML file that the maintainer reviews; Pydantic
   refactors can no longer drift the contract.

A choice is therefore required: which artifact is canonical, the OpenAPI
specification or the Pydantic models?

## Decision

`api/openapi/sbs-api-v1.yaml` is the canonical contract. The Pydantic v2
models in `api/sbs_api/models/` implement the contract. The standalone
JSON Schemas in `api/openapi/schemas/` are exported from the Pydantic
models.

When the OpenAPI specification and the Pydantic models disagree, the
specification wins. The Pydantic models are corrected to match.

The integration test `tests/test_openapi_pydantic_match.py` asserts the
two sides agree on:

- Required fields per shared model.
- Property names per shared model.
- Property types (including enum value sets, nullability, format hints).
- The RFC 9457 required minimum on `ProblemDetail`.
- The OpenAPI 3.1 version pin.
- The `info.version` alignment with the standards-pack schema_version
  pattern.

Cosmetic differences — property ordering inside the YAML and JSON,
`$defs` (Pydantic) vs `components.schemas` (OpenAPI) placement of
enums, `examples` location at field-level versus schema-level — are
tolerated. The test does not enforce byte-level equality; it enforces
semantic agreement.

## Precedent

Cite from
[docs/research/market-comparators.md §5.A](../research/market-comparators.md#5a-api-and-schema-layer).
The standards-pack table in §5.A enumerates the OpenAPI specification as
the **first** artifact a regulator publishes alongside JSON Schema,
validation rules, code lists, batch manifest, sample payloads, and an
error catalogue. The pattern is *the specification is the artifact*; the
implementation behind it is a vendor choice.

The UK Open Banking Implementation Entity publishes its OpenAPI
specifications as the canonical contract; reference implementations
(Java, .NET) are downstream. The CFPB Consumer Complaint Database has a
public API documented by an OAS document; the implementation behind it
is internal and not part of the contract. The European Banking Authority's
Data Point Model + XBRL taxonomy is curated separately from any reporting
software that consumes it. In every comparator,
*the specification is curated; the implementation is downstream*.

Cite also
[docs/research/2026-05-18-prompt-05-stack-validation.md §A](../research/2026-05-18-prompt-05-stack-validation.md#a-openapi-31-as-the-canonical-contract-format)
for the per-choice production-readiness verdict on OpenAPI 3.1 as the
specification format, and §B for the verdict that Pydantic v2 is the
right *implementation* library under this contract-canonical pattern.

## Divergence

This decision diverges from FastAPI's default Pydantic-first pattern. We
diverge because the institution-facing audience values *spec stability*
over Python ergonomics. Pydantic refactors should not silently rewrite a
published regulator contract.

A second divergence is from "generate the OpenAPI from Pydantic via
`app.openapi()` at runtime." We diverge because runtime-generated specs
carry Pydantic-specific artifact noise (`$ref` shapes that name internal
Pydantic types, ordering quirks, `additionalProperties` inheritance
defaults), which makes the specification harder to read and review. A
hand-curated YAML file is reviewable; a runtime-generated artifact is
not.

A third divergence is from "treat the standalone JSON Schemas as
canonical alongside the OpenAPI specification." We diverge because two
canonical artifacts produce a tie-breaker ambiguity. Standalone JSON
Schemas are exported from Pydantic; Pydantic implements the OpenAPI;
the OpenAPI is the contract. The chain is deterministic and the
match-test enforces it.

## Consequences

- Contract changes are YAML edits, reviewed by a human. Pydantic refactors
  that fail the match-test do not land; the test gates merges.
- The schema export script (`scripts/regenerate-schemas.sh`) must be run
  whenever the Pydantic models change. The schemas are a committed
  artifact, not a build-time output. Reviewers see schema diffs alongside
  model diffs.
- The FastAPI scaffold that lands in Prompt 6 will *not* use
  `FastAPI(openapi_url=...)`'s default Pydantic-generated spec. Instead,
  the scaffold serves the curated YAML file at `/openapi.yaml` and
  optionally at `/openapi.json`; the runtime never re-derives the spec.
- The match-test (`tests/test_openapi_pydantic_match.py`) is the gate.
  It is the closest the project has, at this stage, to a "contract test"
  — institutions integrating against the spec are not yet running it,
  but the test ensures the spec and the implementation cannot drift.
  When the conformance suite lands in Part 7 (post-May 25), it
  supersedes this internal test as the load-bearing alignment check.
- If at some future point Pydantic v2 is replaced by another validation
  library (a re-platforming decision discussed in the
  [stack-validation note §B](../research/2026-05-18-prompt-05-stack-validation.md#b-pydantic-v2-for-request-and-response-validation)),
  the contract does not change. Only the implementation does.

## Amendments

### 2026-05-19 — full HMAC canonical request contract (Prompt 7)

The OpenAPI spec landed the `hmac_signature` security scheme declaration
in Prompt 5 with the canonical request format marked TBD. This
amendment fills in that TBD. The wire shape itself is documented here
because it is part of the *contract*, not the implementation; SDK
authors generate signing code from this section.

**Headers.** Two request headers carry the signature:

- `X-SBS-Timestamp: <RFC 3339 UTC>` — e.g., `2026-05-19T14:23:45Z`. The
  timestamp is the request creation time at the client. Clock skew
  tolerance is **5 minutes** (±300 seconds) against the server's UTC
  clock.
- `X-SBS-Signature: hmac-sha256-v1=<base64>` — the algorithm version
  prefix (`hmac-sha256-v1`) supports future rotation to a different
  algorithm or key-derivation scheme without breaking clients.

**Canonical request string.** Six lines joined with `\n`:

```
<HTTP-method-uppercase>
<request-target-as-on-the-wire>
<lowercased-host-header>
<X-SBS-Timestamp-value>
<lowercase-hex(sha256(body))>
<institution_id>
```

Worked example (POST /v1/complaints, sandbox host, empty-body placeholder):

```
POST
/v1/complaints
sbs-suptech-sandbox.local
2026-05-19T14:23:45Z
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
BANCO_DEMO_001
```

Where:

- `HTTP-method-uppercase` is `GET`, `POST`, `PATCH`, etc.
- `request-target-as-on-the-wire` is the path-and-query as received,
  e.g., `/v1/complaints?cursor=abc&limit=20`. Query parameters are kept
  in the order the client sent them; the server does not canonicalise.
- `lowercased-host-header` is the value of the inbound `Host` header
  lowercased (no port unless the client included one). Binding the host
  prevents cross-environment signature replay if a secret is ever shared
  between sandbox and production. This follows AWS SigV4 §Task 1, which
  signs `host` for the same reason.
- `X-SBS-Timestamp-value` is the verbatim header value.
- `lowercase-hex(sha256(body))` is the SHA-256 of the raw request body,
  lowercase hex. Empty body produces the constant
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- `institution_id` is the value the client expects the server to bind
  the request to (it is cross-checked against the mTLS subject; a
  mismatch returns 401 `SIGNATURE_INSTITUTION_MISMATCH`).

**Body-hash specification.**

- The hash is SHA-256 over the request body *bytes as the server reads
  them* — after HTTP/1.1 dechunking, before any content-decoding such
  as gzip. The client computes the hash over the same bytes it will
  send on the wire.
- For multipart batch upload (`POST /v1/batches`), the hash is over the
  full multipart payload including boundary delimiters
  (`--<boundary>` and the trailing `--<boundary>--`), computed by the
  client before transmission. The SDK must finalise the multipart
  encoding *before* hashing.
- Empty body hashes to the SHA-256 of the empty octet stream:
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

**Signature.**
`base64(hmac_sha256(key=institution_secret, msg=canonical_request_string))`.
The secret is per-institution and stored encrypted at rest (see
`institution_secrets`). Rotation is supported with an
`active_secret` and a `previous_secret` window; a request signed with
the previous secret is accepted for the duration of the configured
grace window (`SBS_API_HMAC_SECRET_ROTATION_GRACE_SECONDS`, default
3600).

**Replay protection.** A Redis SET with key
`sbs:hmac:replay:<institution_id>:<sha256(signature)[:16]>` and TTL of
**10 minutes** — derived as `timestamp_skew × 2 + 5% headroom`
(`300s × 2 = 600s`; the 5% headroom is the +30s the implementation
configures via `SBS_API_HMAC_REPLAY_CACHE_TTL_SECONDS=600`, treating
the headroom as already absorbed by Redis's clock granularity at this
scale). Replays inside the window return 401 `SIGNATURE_REPLAYED`. The
TTL is deliberately short: the timestamp check is the primary defence,
and the replay cache is the defence-in-depth backstop bounded by the
skew window. The original 24-hour figure was a memory-pressure error
caught in the pre-workstream-A pressure test.

**Constant-time comparison.** Signature comparison MUST use a
constant-time primitive — `hmac.compare_digest` in Python,
`crypto/subtle.ConstantTimeCompare` in Go,
`CryptographicOperations.FixedTimeEquals` in .NET. A naive `==` over
bytes leaks signature length and prefix to a timing attacker.

**Stable error codes.** `SIGNATURE_MISSING_HEADER`,
`SIGNATURE_ALGORITHM_UNSUPPORTED`, `SIGNATURE_INVALID`,
`SIGNATURE_EXPIRED`, `SIGNATURE_REPLAYED`,
`SIGNATURE_INSTITUTION_MISMATCH`. All return 401 with ProblemDetail.

**Precedent for the canonical-request shape.**
[docs/research/market-comparators.md §5.A.M](../research/market-comparators.md#5am-authentication-signing-and-rate-limiting-for-regulator-facing-apis)
cites
[**AWS SigV4 §Task 1 (CreateCanonicalRequest)**](https://docs.aws.amazon.com/general/latest/gr/sigv4-create-canonical-request.html)
as the single solid precedent. The SBS shape is a minimal subset: SigV4
canonicalises headers and signed-headers list, which the SBS contract
does not need because the regulator API has a fixed header surface. The
shape is otherwise the same — method, target, timestamp, body hash,
identity.

**Backward compatibility.** The OpenAPI security scheme declaration is
unchanged; only its prose description is expanded to point to this
amendment. SDKs generated from the spec do not need regeneration unless
they incorporate the signing logic itself (the canonical-request
construction).

**Deployment note for proxy-mode mTLS.** The HMAC signature is over the
request-target *byte-identical* to what the client sent. Reverse
proxies that re-write or normalise the URI break the signature. Envoy
preserves `:path` byte-identical by default. Nginx must use
`proxy_pass http://upstream$request_uri;` rather than relying on URI
normalisation; the `merge_slashes off;` directive may also be required
when the client legitimately sends `//` in a path. The smoke test
exercises this path against the dev CA in `direct` mode; the production
overlay must include a conformance test against the deployed proxy
before the chain is considered intact.

### 2026-05-20 — multipart body-hash redefinition + outbound response signing + X-SBS-Key-Id (Prompt 8)

This amendment supersedes the multipart body-hash specification from
the 2026-05-19 amendment, adds an outbound (server-to-institution)
signing mirror of the inbound contract, and introduces a third
signing header `X-SBS-Key-Id` used in both directions.

**Multipart body-hash (inbound) — supersedes the prior definition.**
The 2026-05-19 amendment said the hash was over "the full multipart
payload including boundary delimiters". That definition is wrong in
practice: boundary encoding is implementation-detail-dependent, so two
HTTP clients producing identical CSV uploads would compute different
canonical-request hashes purely from boundary choice. The replacement
definition:

For `POST /v1/batches` (and any future multipart endpoint), the
`body-hash` line of the canonical request is the **SHA-256 of the
CSV file bytes only** — not the SHA-256 of the multipart envelope,
not the SHA-256 of the manifest JSON, not the SHA-256 of the
concatenation.

Rationale. The manifest declares the CSV's `checksum_sha256` as an
independently-verifiable field; the server compares it against the
actually-received CSV bytes. So the manifest hash is redundant as a
signing input. Signing the CSV bytes directly means the institution's
signing client computes one hash (over the file they're uploading) and
the server's verifier computes the same hash on receipt. The multipart
boundary encoding does not affect the signature. The `Content-Length`
of the multipart envelope is *not* part of the canonical request
because boundary length is implementation-detail-dependent.

The non-multipart canonical request (for JSON-body endpoints) is
unchanged: `lowercase-hex(sha256(request-body-bytes))`.

**Outbound response signing.** The same canonical request shape
applies in both directions. Five lines:

```
<HTTP-method-uppercase>
<callback-path>
<X-SBS-Timestamp-value>
<lowercase-hex(sha256(body))>
<institution_id>
```

Direction differs only in which secret is used and which side
verifies:

- **Inbound (institution → SBS)** uses the institution's *inbound*
  secret from `institution_secrets.active_secret`. SBS verifies.
- **Outbound (SBS → institution)** uses the institution's
  *outbound* secret from `outbound_webhook_secrets.active_secret`.
  The institution verifies (per the SDK recipe).

The two secrets are stored in separate tables to support independent
rotation. Both tables carry a `kid` column to enable rolling-secret
rotation in the future (active + previous secrets keyed by `kid`);
currently `kid=sandbox-v1` everywhere. Both share the 5-minute clock
skew tolerance. Replay protection is server-side enforced for inbound
only — the outbound side does not enforce on the receiving
institution's behalf, because that is the institution's
responsibility per their verification recipe.

**`X-SBS-Key-Id` header — new third signing header.** Both inbound
and outbound requests include `X-SBS-Key-Id` alongside
`X-SBS-Timestamp` and `X-SBS-Signature`. Value is `sandbox-v1` from
day one, mirroring the OAuth `kid=sandbox-v1` pattern from ADR 0032.
The server (inbound) or the institution (outbound) selects the
secret to verify against by `kid` lookup, not by trial-decryption
through the active and previous slots. Future rotation rolls in a
new `kid` (e.g., `sandbox-v2`); the previous secret stays valid in
the `active` slot until cutover, then is moved to `previous` for the
grace window, then retired.

The `X-SBS-Key-Id` value is not itself part of the canonical request
string — it is metadata that tells the verifier which secret to
load. The signed contents (method, target, timestamp, body-hash,
institution_id) are unchanged.

**Backward compatibility for inbound.** Existing inbound clients
that do not send `X-SBS-Key-Id` continue to work in Prompt 8: the
server falls back to the `active_secret` for the institution when
the header is absent. The header becomes required in Prompt 9
alongside the SDK rollout. The smoke test sends the header from this
prompt forward so the canonical demo path exercises it.

**Headers on every outbound callback (new):**

```
X-SBS-Timestamp: 2026-05-20T14:23:45Z
X-SBS-Signature: hmac-sha256-v1=<base64>
X-SBS-Key-Id: sandbox-v1
```

**Retry policy (outbound).** Exponential backoff: 30 seconds,
2 minutes, 10 minutes, 1 hour, 6 hours — 5 attempts total, ~7.7-hour
window. Persistent failures recorded in `webhook_deliveries` with
status `delivery_failed`. See ADR 0035 for the full outbound webhook
contract.

**Stable error codes (additions).** `WEBHOOK_URL_REJECTED` (the
configured webhook URL failed the SSRF prevention checks; no retry
attempted). All other inbound codes from the prior amendment are
unchanged.

**Precedent.** [docs/research/market-comparators.md §5.A.M](../research/market-comparators.md#5am-authentication-signing-and-rate-limiting-for-regulator-facing-apis)
is extended in Prompt 8 to cover the outbound mirror of the inbound
signing contract. **Stripe webhooks** is the canonical outbound
reference: same HMAC primitive, same timestamp+signature header
pair, exponential-backoff retry, persistent failure recording. The
`X-SBS-Key-Id` header follows the JWT `kid` pattern adopted in
ADR 0032 for the same reason — explicit key selection beats trial-
decryption when a rotation is in flight.
