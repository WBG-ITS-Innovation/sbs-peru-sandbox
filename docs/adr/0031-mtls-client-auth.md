# ADR 0031 — mTLS client authentication contract

- **Status:** Accepted
- **Date:** 2026-05-19
- **Target prompt / Part:** Prompt 7 / Part 3
- **Supersedes:** ADR 0003 (jointly with ADR 0032 and the ADR 0027 HMAC amendment)
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

Prompt 6 closed Part 2 with a fail-closed authentication stub: when
`AUTH_STUB_ENABLED=false` every tenant-binding endpoint returns 503
`AUTH_NOT_CONFIGURED`. The stub is a foot-gun mitigation, not a security
control. Prompt 7 must replace it with a real authentication chain that
matches both the regulator-grade audience expectation and the production
posture SBS will operate behind a reverse proxy.

Three loosely-coupled mechanisms together form that chain:

1. **mTLS** — *who is connecting.* The TLS handshake authenticates the
   institution by certificate. This is the property a regulator cares
   about most: every byte on the wire is provably from a named institution
   that holds a private key issued by the SBS CA.
2. **OAuth 2.0 client_credentials** — *what they may do.* The bearer token
   carries the scopes the institution is authorised for; the API enforces
   per-scope policy. This is ADR 0032.
3. **HMAC request signing** — *what they actually sent.* The signature
   binds the request body and a timestamp so an attacker who somehow
   reaches the TLS endpoint with a stolen connection cannot replay or
   re-shape a previous request. This is the ADR 0027 amendment.

This ADR locks the mTLS layer. The other two ADRs lock the rest of the
chain. The three together replace ADR 0003 ("api-authentication") which
was a single Proposed ADR covering all three mechanisms.

## Decision

**Cert is the institution identity.** All non-public endpoints require a
valid client certificate issued by the SBS CA. In the sandbox the CA is
the dev CA produced by `scripts/dev-ca.sh`; in production it is the SBS
PKI. The CN of the leaf certificate is the institution identifier, e.g.
`CN=BANCO_DEMO_001`. SAN is reserved for future use (e.g. multiple
institutions sharing a key custodian); the runtime reads CN only.

**Cert validation.** The TLS layer enforces, per request:

- Chain to the SBS CA root (sandbox: `dev-ca/ca.pem`; production: the
  PKI's root bundle loaded by the reverse proxy).
- Not expired (`notBefore` and `notAfter`).
- Not in the revocation list. Sandbox: in-memory list seeded at boot,
  mutable via an admin endpoint (deferred to Part 8). Production: CRL or
  OCSP; the choice is a Part 9 production-readiness decision.

**Two operating modes.** The runtime supports both direct termination (the
sandbox path) and reverse-proxy termination (the production path),
selected by `SBS_API_MTLS_MODE`:

- `direct` — uvicorn is configured with
  `ssl_certfile`, `ssl_keyfile`, `ssl_ca_certs`, and
  `ssl_cert_reqs=ssl.CERT_REQUIRED`. The verified peer cert is in the ASGI
  scope; the runtime extracts the DN from there.
- `proxy` — the reverse proxy terminates TLS, validates the cert against
  the SBS CA root, and forwards the verified DN in a trusted header
  (`X-Client-Cert-DN`). The runtime trusts the header *only because* the
  network path from proxy to runtime is itself mTLS-protected (deferred to
  the Helm chart in Part 9).

**Dependency surface.** A FastAPI dependency `verified_mtls_subject`
returns a `MtlsSubject(institution_id: str, cert_thumbprint: bytes)`
record. Every protected route declares it (or a downstream dependency
that consumes it). The same dependency is the input to the OAuth
cert-binding check in ADR 0032.

**Storage.** A new table `institution_certificates` carries
`(institution_id, cn, sha256_thumbprint, not_before, not_after,
revoked_at)`. The CN→`institution_id` mapping is read from this table;
unknown CNs return 403 with stable code `CERT_CN_UNKNOWN`.

**Stable error codes.** mTLS-layer failures return RFC 9457 problem+json:

| Code | HTTP | Trigger |
| --- | --- | --- |
| `CERT_REQUIRED` | 401 | No client cert presented when one was required. |
| `CERT_INVALID` | 401 | Cert failed chain or signature validation. |
| `CERT_EXPIRED` | 401 | `notAfter` is in the past. |
| `CERT_CN_UNKNOWN` | 403 | Cert is valid but CN is not in `institution_certificates`. |
| `CERT_REVOKED` | 403 | Cert is in the revocation list. |

## Precedent

[docs/research/market-comparators.md §5.A.M](../research/market-comparators.md#5am-authentication-signing-and-rate-limiting-for-regulator-facing-apis)
is the regulator-domain precedent for the mTLS + OAuth + HMAC chain. The
single solid precedent the new subsection cites is the **UK Open Banking
Read/Write Data API**, which uses exactly this pattern: mTLS for
institutional authentication; OAuth tokens for scope authorisation; and
RFC 8705 cert-thumbprint binding so a stolen bearer token cannot be
replayed from a different connection.

The protocol-level precedent for the cert-binding step is
[RFC 8705 §3](https://datatracker.ietf.org/doc/html/rfc8705#section-3),
"Mutual TLS Client Authentication." Open Banking UK's specification
references the RFC verbatim, which is the regulator-domain confirmation
that "RFC 8705 as written" is a sufficient design.

## Divergence

We diverge from a *bearer-token-only* posture (the FastAPI tutorial
default, and the convention in many internal APIs) because the
institution-facing audience needs cryptographic proof of identity at the
TLS layer. A leaked bearer token without the matching cert is unusable;
this property is what makes the May 25 demo claim ("every request you see
is mTLS-authenticated") true rather than aspirational.

We diverge from *SAN-as-identifier* (an alternative reading of the
WebPKI conventions) because the Open Banking UK precedent uses CN and we
do not have a regulator-specific reason to depart. SAN is reserved
should a future use case require it (e.g., one cert binding to two
institution_ids during a corporate restructure).

We diverge from *certificate-pinning at the SDK* (a stricter posture
some payment APIs adopt) because pinning interacts badly with the
institutional CA rotation procedures that SBS will need. The CA chain
validation is the SBS PKI's responsibility; pinning is not.

## Consequences

- The dev CA (`scripts/dev-ca.sh`) is idempotent and gitignored. Two
  leaf certs are issued at sandbox bring-up: `BANCO_DEMO_001` and
  `COOPAC_DEMO_002`. The smoke test exercises both.
- `scripts/run-api.sh` is mTLS-aware: when `dev-ca/` is present and
  `SBS_API_MTLS_MODE=direct`, uvicorn is started with the SSL kwargs;
  otherwise it falls back to plain HTTP for tests that do not exercise
  the auth chain. The fallback is gated by an explicit
  `SBS_API_DISABLE_MTLS_FOR_TESTS=true` flag — production overlays do
  not set it.
- Revocation in the sandbox is operationally light: an in-memory list,
  mutable via an admin endpoint that lands in Part 8. A production
  posture requires CRL or OCSP and is deferred to Part 9 alongside the
  Helm chart, where the chart can mount a CRL volume or wire OCSP into
  the reverse proxy.
- Cert rotation procedures (institution receives a new cert N days
  before the old one expires, both valid during the grace window) are
  operational and deferred to Part 9. The data model already supports
  multiple active certs per institution because the
  `institution_certificates` table has no uniqueness on
  `institution_id`; uniqueness is on `sha256_thumbprint`.
- The `MtlsSubject.cert_thumbprint` field is the input to ADR 0032's
  cert-bound OAuth token check. Removing the thumbprint would break that
  binding; the field is load-bearing.
