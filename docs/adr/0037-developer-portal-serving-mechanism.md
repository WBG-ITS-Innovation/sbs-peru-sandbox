# ADR 0037 — Developer portal serving mechanism

- **Status:** Accepted
- **Date:** 2026-05-20
- **Target prompt / Part:** Prompt 9 / Part 7
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

Prompt 5 shipped a development-only developer portal at
`api/devportal/index.html` that loaded Stoplight Elements assets from
unpkg via CDN with SRI hashes. The file header explicitly named this
as a developer-workstation aid and deferred a deployment-grade portal
to Prompt 9.

Prompt 9 closes Part 7 (developer-portal-and-onboarding). The portal
is the surface an institutional integrator (Diego the Compliance
Officer, Patricia the Operations Manager, Roberto the COOPAC risk
officer) opens first. The Lima sprint kickoff on May 25 demonstrates
the portal against a venue wifi that is not under regulator control;
a CDN that is unreachable during the demonstration is a demo-day
failure for the first impression institutions will have of the API.

The framing question is two-part: (1) where do the Stoplight Elements
JavaScript and CSS assets come from at request time — a CDN, or the
running application itself, and (2) how is the portal HTML served —
as a static asset from a separate process, or by the existing FastAPI
application that already serves the canonical OpenAPI YAML at
`/v1/openapi.yaml`.

A third, smaller question is the security posture for serving the
vendored asset files: a `StaticFiles` mount serves any file in the
mount directory, which is a path-traversal surface; an explicit
allowlist constant in a path-parameter route is more conservative.

## Decision

1. **Vendor Stoplight Elements locally to `vendor/stoplight-elements/`.**
   No CDN. The vendored directory contains
   `web-components.min.js`, `styles.min.css`, the upstream
   `LICENSE` (Apache 2.0), and a `VENDOR.md` recording the upstream
   version, fetch URL, SHA256 of each file, and date fetched. The
   portal HTML template references only local asset paths.
   Re-vendoring is a manual step documented in CONTRIBUTING.md.

2. **Serve the portal from the existing FastAPI application** at two
   routes registered under the `/v1` prefix: `GET /v1/portal/`
   returns the portal HTML, `GET /v1/portal/assets/{filename}`
   returns one of the vendored asset files. Both routes are public
   — no `OAuthDependency`, no `MtlsSubject`, no scope check. The
   portal-asset route is implemented as a **path-parameter route
   with an explicit filename allowlist**, not a `StaticFiles` mount.

3. **Explicit filename allowlist and explicit media-type map.** A
   module-level `VENDOR_ASSET_ALLOWLIST = frozenset({
   "web-components.min.js", "styles.min.css", "LICENSE"})` is the
   complete set of files the portal-asset route will serve. A
   companion `VENDOR_ASSET_MEDIA_TYPES` dict maps each allowlisted
   filename to its `Content-Type`. Anything else returns 404, the
   same defensive 404 posture the institution-binding code uses (no
   error message that would inform a re-vendoring contributor; the
   re-vendoring procedure in CONTRIBUTING.md is what informs them).

4. **Cache-Control on vendored assets.** `Cache-Control: public,
   max-age=31536000, immutable`. The vendored assets are immutable
   for the lifetime of a deployment; re-vendoring requires a new
   deploy, which invalidates the URL space at the boundary.

5. **"Try It" disabled in the portal HTML.** The Stoplight
   `tryItCredentialsPolicy="omit"` configuration plus a code comment
   in the template explain why: the API's mTLS + OAuth + HMAC auth
   chain cannot be satisfied from a browser-based UI. Integrators
   use the helper + curl path the portal documents.

6. **Public routes declared in the OpenAPI spec with `security: []`.**
   The two portal routes are added to the canonical spec with an
   explicit empty security array so the no-auth contract is part of
   the published documentation.

7. **Orphaned `ValidBatchManifest` example removed from the spec in
   the same workstream** so the spec the portal renders is Spectral-
   clean. The cleanup is not new behaviour; the example was unused
   from inception and Spectral has been warning on it since Prompt 8.

## Precedent

[docs/research/market-comparators.md §5.A.P](../research/market-comparators.md#5ap-developer-portal-serving-choices-added-prompt-9-for-adr-0037)
is the load-bearing reference. The convergent regulator-domain
pattern is: the regulator publishes the source spec under version
control; the rendered portal is served from regulator-controlled
infrastructure rather than a vendor CDN. Open Banking UK, Brazil
Open Finance, and Australian CDR all self-host their portals.
Vendoring the renderer assets in addition (the strict variant of
self-hosting) is the conservative default for a demonstration in
a controlled venue with venue-controlled wifi.

The "Try It"-disabled posture follows Open Banking UK: the portal
is documentation; integration uses the published helper code, the
PKI test endpoints, and curl. This matches §5.A.P's framing that the
browser-based "Try It" cannot satisfy mTLS in any case.

The "explicit allowlist over StaticFiles mount" choice is a
defence-in-depth pattern documented in OWASP's path-traversal
prevention cheat sheet: a positive allowlist is conservative against
encoding tricks (URL-encoded, double-encoded, Unicode normalization,
null-byte injection) that path-resolution checks sometimes miss.

## Divergence

We diverge from Open Banking UK's partial-vendoring posture (OBIE
relies on a CDN for some renderer assets while committing the spec
itself). The Lima venue wifi risk is the load-bearing reason for
strict vendoring; OBIE's portal does not have the same demonstration-
venue constraint. The cost is ~2.4 MB of committed JavaScript and
CSS that must be re-vendored on Stoplight Elements security
updates.

We diverge from the simpler `StaticFiles` mount approach. A path-
parameter route with an allowlist costs ~10 lines of code; the
trade-off is that re-vendoring requires updating the directory AND
the allowlist constant AND the media-type map. CONTRIBUTING.md
documents this triple-update requirement near the allowlist
constant, not buried in the route module. New assets that aren't
allowlisted return 404 silently — that's a feature for the security
posture and a friction point for re-vendoring; the friction is
acceptable because re-vendoring is a low-frequency operation.

We diverge from publishing the portal at a separate hostname or
process. Serving from the same FastAPI process matches the one-
command-deploy north-star principle and means the portal shares the
API's TLS / mTLS / observability surface without separate plumbing.

We diverge from any redirect-or-rewrite path that would let
`/v1/portal` (no trailing slash) work. FastAPI's default behaviour
is the contract: the canonical path includes the trailing slash.

## Consequences

- The `vendor/stoplight-elements/` directory adds ~2.4 MB to the
  repository (`web-components.min.js` is ~2.0 MB and
  `styles.min.css` is ~290 KB at version 9.0.19). The Apache 2.0
  LICENSE is committed alongside so the licensing is explicit and
  auditable. The size cost is documented in
  [vendor/stoplight-elements/VENDOR.md](../../vendor/stoplight-elements/VENDOR.md).

- Re-vendoring is a manual step. CONTRIBUTING.md documents the
  procedure: fetch the new version from unpkg, verify the SHA256
  against the upstream's published checksum, update `VENDOR.md`,
  update the allowlist and media-type map if filenames change.

- The portal routes are unauthenticated. The OpenAPI spec declares
  them with `security: []`. An institution that hits
  `/v1/portal/` without credentials gets the documentation; this is
  intentional and matches the regulator-domain pattern of public-
  documentation, credentialed-integration.

- The "Try It" disablement is documented in the portal HTML so
  future contributors understand the rationale. Integrators who
  want to actually invoke an endpoint use the SDK helpers and curl
  flows the portal documents.

- The `ValidBatchManifest` example removal is invisible to
  integrators (it was orphan content) and visible to Spectral
  (the lint warning is gone). The OpenAPI spec the portal renders
  is Spectral-clean as of this prompt.

- Path-traversal test coverage is explicit: six form attempts
  (`../etag.py`, `..%2Fetag.py`, `..%252Fetag.py`,
  `../../../etc/passwd`, `etag.py%00.js`, `..\etag.py`) ALL return
  404. The allowlist-not-resolve approach makes this trivially
  true; the tests are belt-and-braces.

- A manual browser-render check (Chrome or Firefox, no console
  errors) is part of the exit gate. The HTTP-level checks (200,
  Content-Type, Cache-Control) verify the bytes get served; only a
  real browser confirms the web component initializes — CSP
  issues, Stoplight upstream changes, or path mismatches would
  pass the HTTP checks while failing the render.
