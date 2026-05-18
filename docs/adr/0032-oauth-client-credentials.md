# ADR 0032 — OAuth 2.0 client_credentials scopes and token semantics

- **Status:** Accepted
- **Date:** 2026-05-19
- **Target prompt / Part:** Prompt 7 / Part 3
- **Supersedes:** ADR 0003 (jointly with ADR 0031 and the ADR 0027 HMAC amendment)
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

mTLS (ADR 0031) authenticates *who is connecting*. OAuth answers *what
they may do*. The institution-facing API has operations of materially
different sensitivity: writing a complaint, reading complaints back,
uploading a batch, and reading sandbox-internal diagnostics. A single
"authenticated" bit is too coarse for the regulator-grade audience; each
operation needs an explicit scope so a partner who is authorised to
upload batches but not authorised to read other institutions' write
endpoints cannot do so by accident.

Prompt 7 lands the token endpoint, the four scopes, the cert-binding
check from RFC 8705, and the per-endpoint scope-enforcement dependency.
This ADR locks the contract; ADR 0010 ("SDK distribution and versioning")
will name the scope-discovery story for SDK callers when it lands in
Part 7.

## Decision

**Grant type.** OAuth 2.0 *client_credentials* per
[RFC 6749 §4.4](https://datatracker.ietf.org/doc/html/rfc6749#section-4.4).
Authorization-code, implicit, password, and refresh flows are not
supported — there is no end user to delegate consent to, and the bearer
token is short-lived enough that a "request a fresh one" pattern is
cheaper than maintaining refresh-token state.

**Token endpoint.** `POST /v1/oauth/token`. Request body is
`application/x-www-form-urlencoded` per RFC 6749 §2.3.1:

```
grant_type=client_credentials
scope=complaints:write batch:upload
```

Client credentials are presented via Basic auth (`Authorization: Basic
<base64(client_id:client_secret)>`). The endpoint additionally requires
a valid mTLS connection from ADR 0031 — credentials without the matching
cert return 401 `TOKEN_CERT_REQUIRED`.

**Token shape.** Sandbox: JWT signed with HS256 using a server-side key
persisted at `dev-ca/oauth-signing-key.bin` (generated at first boot by
`secrets.token_bytes(32)`). Production overlay: RS256 with a Key Vault
key, deferred to Part 9. Claims:

| Claim | Value |
| --- | --- |
| `iss` | `https://sbs-suptech-sandbox.local` (sandbox); SBS public iss in production. |
| `aud` | `sbs-api` |
| `iat` | Token issuance time. |
| `exp` | `iat + 900` seconds (15 minutes). |
| `sub` | `institution_id` from the mTLS subject. |
| `scope` | Space-separated list of granted scopes (subset of requested ∩ permitted). |
| `cnf.x5t#S256` | SHA-256 thumbprint of the presenting cert, per RFC 8705 §3.1. |

**Four scopes.** The full enumeration:

| Scope | Granted operations |
| --- | --- |
| `complaints:write` | `POST /v1/complaints`, `PATCH /v1/complaints/{id}/status` |
| `complaints:read` | `GET /v1/complaints`, `GET /v1/complaints/{id}` |
| `batch:upload` | `POST /v1/batches`, `GET /v1/batches/{id}` |
| `status:read` | `GET /v1/status/*` (sandbox-internal diagnostics) |

The scope-to-operation mapping is canonical. A change to it is an ADR
amendment.

**Per-endpoint enforcement.** A FastAPI dependency
`verified_oauth_token_with_scope(*required_scopes)` is declared on each
protected route. It validates the JWT signature, checks `iss`, `aud`,
`exp`, recomputes the `cnf.x5t#S256` thumbprint against the current
connection's mTLS subject, and enforces that *all* required scopes are
present in the `scope` claim. Failure modes are stable:

| Code | HTTP | Trigger |
| --- | --- | --- |
| `TOKEN_REQUIRED` | 401 | No `Authorization: Bearer` header. |
| `TOKEN_INVALID` | 401 | JWT signature or structural validation failed. |
| `TOKEN_EXPIRED` | 401 | `exp` is in the past. |
| `TOKEN_CERT_THUMBPRINT_MISMATCH` | 401 | `cnf.x5t#S256` ≠ current cert thumbprint. |
| `TOKEN_SCOPE_INSUFFICIENT` | 403 | Required scope is not in the token's `scope` claim. |
| `TOKEN_CERT_REQUIRED` | 401 | Token endpoint hit without a valid mTLS connection. |

**Token TTL is 15 minutes.** Short enough that revocation by
expiry is acceptable in the sandbox; long enough that a typical batch
upload completes inside one token. Clients re-request when expiry
approaches.

**No refresh, no introspection, no revocation list.** Client_credentials
grants do not need refresh tokens. RFC 7662 introspection is deferred to
Part 8 if SBS supervisors need a diagnostic endpoint. Revocation is by
client_secret rotation; the short TTL makes a server-side revocation
list unnecessary.

## Precedent

[docs/research/market-comparators.md §5.A.M](../research/market-comparators.md#5am-authentication-signing-and-rate-limiting-for-regulator-facing-apis)
cites the **UK Open Banking Read/Write API Specification §5.2 (Access
Tokens)** as the single solid precedent for this scope shape. Open
Banking UK uses the same write/read/upload separation and the same RFC
8705 cert-binding pattern. The Brazilian Open Finance specification
adopts the same shape (and we noted it in §5.A.M without citing it as
the load-bearing reference — Open Banking UK has the longer production
record).

## Divergence

We diverge from *symmetric scopes* (a single `complaints` scope covering
both read and write) because the institutional integration profile we
expect — large banks integrate against `complaints:write` first, the
read endpoints only after their reconciliation workflow is in place —
benefits from being able to grant the write scope without the read
scope.

We diverge from *refresh tokens* (a default many API templates carry)
because client_credentials grants have no end-user delegation to refresh
and the 15-minute TTL is short enough that re-authentication is cheap.

We diverge from *bearer-token-only* (no cert binding) for the reasons in
ADR 0031: a stolen token without the matching cert must be unusable.

We diverge from *opaque tokens with introspection* (the alternative to
self-contained JWTs) because the sandbox does not need the
revocation-by-introspection property and self-contained JWTs are cheaper
to verify (no round-trip to a token-info service per request). When SBS
operationalises a token-info service in Part 8, this ADR is amended.

## Consequences

- The token endpoint shares the mTLS dependency with every other
  protected endpoint. The client must present the cert *during the token
  request*, not only when calling the protected endpoint — this is what
  binds the cert to the token via `cnf.x5t#S256`.
- The HS256 → RS256 transition for production is a one-line change in
  the signing-key load path, plus a Key Vault integration. The claim
  shape does not change; SDK consumers do not see a migration.
- The four scopes are stable and small. Adding a fifth (e.g.
  `auditlog:read` when Part 6 ships the audit log endpoint) is an ADR
  amendment; renaming an existing scope is a breaking change and
  requires a new version-2 token format.
- Per-endpoint scope enforcement is declarative. A new endpoint that
  needs an unusual combination (e.g., a Part 6 "supervisor analyst" path
  needing both `complaints:read` and `auditlog:read`) declares both in
  the dependency. The enforcement code does not change.
- The sandbox's signing-key on disk is a known sandbox-grade choice. The
  second-opinion subagent is expected to flag it; the flag is
  acknowledged and the production posture is deferred to Part 9 (Key
  Vault, hardware-backed where the operator chooses).
