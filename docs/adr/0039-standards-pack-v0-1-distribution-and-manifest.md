# ADR 0039 — Standards pack v0.1 distribution and manifest

- **Status:** Accepted
- **Date:** 2026-05-20
- **Target prompt / Part:** Prompt 9 / Part 7
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

The standards pack is the single download an institutional
integrator opens after reading the portal. It bundles the OpenAPI
spec, the JSON schemas, the error catalog, the SDK helpers, the
recipes, the example payloads, a provenance manifest, and a
checksums file. The pack is what closes the gap between "here is a
specification" and "here is what to do with it".

Three framing questions:

1. **Distribution mechanism.** GitHub release tarball, OCI artifact,
   PyPI / npm packages, a separate download portal, or something
   else.

2. **Manifest shape.** What fields the `manifest.json` declares so
   integrators have a stable, machine-readable provenance record.

3. **Integrity vs authenticity.** Whether a `checksums.sha256` is
   sufficient or whether the pack needs SLSA + cosign attestation
   from v0.1.

These choices interact with [ADR 0013](0013-standards-pack-distribution.md)
(Proposed, Part 11) which targets the full standards-distribution
decision. ADR 0039 is the v0.1 scope: the minimum viable bundle for
the May 25 sprint, with an explicit upgrade path documented to the
production posture.

A fourth, smaller question is the license declaration. WBG legal
review on the final license selection (Apache 2.0 vs. regulator-
publication-public-domain vs. other) is not yet complete.
Publishing the pack with no license is wrong; publishing with a
guessed license is wrong; the right answer is an SPDX-conforming
placeholder that signals "license selection pending".

## Decision

1. **Distribution as a versioned tarball attached to a GitHub
   release.** Output artifact: `dist/standards-pack-v0.1.0.tar.gz`
   with companion `dist/standards-pack-v0.1.0.tar.gz.sha256`.
   `scripts/build-standards-pack.sh` is the build pipeline;
   `make standards-pack` is the convenience invocation. CI
   validates the build on every PR touching `standards-pack/` or
   `sdk-helpers/`.

2. **Manifest shape required at `standards-pack/manifest.json`** —
   schema-validated against `standards-pack/manifest.schema.json`
   (committed in the pack itself so consumers can validate):

   ```json
   {
     "manifest_schema_version": "0.1.0",
     "name": "sbs-complaints-standards-pack",
     "version": "0.1.0",
     "status": "sandbox",
     "publisher": "SBS Peru via WBG ITS Innovation Office",
     "license": "LicenseRef-sandbox-pending-legal-review",
     "git_commit": "<full SHA at build time>",
     "generated_at": "<RFC 3339 UTC timestamp>",
     "portal_url": "https://<sandbox-host>/v1/portal/",
     "webhook_signature_version": "v1",
     "api_server_compatibility": {
       "min_version": "0.1.0",
       "exclusive_max_version": "1.0.0"
     },
     "contains": ["openapi", "schemas", "catalogs", "sdk-helpers",
       "examples", "recipes"]
   }
   ```

3. **License placeholder uses the SPDX `LicenseRef-` mechanism.**
   The value `LicenseRef-sandbox-pending-legal-review` is SPDX-
   conforming (the `LicenseRef-` prefix is the SPDX specification's
   defined mechanism for non-standard identifiers). SPDX-aware
   tooling that reads the manifest accepts this value as valid; a
   plain free-text string like `"sandbox-only"` would be rejected.

4. **Two pack-level documentation fields beyond the minimum.**
   `portal_url` is the canonical link from the offline tarball
   back to the running portal so integrators can rediscover live
   documentation. `webhook_signature_version` declares which
   version of the signature canonical-request shape this snapshot
   reflects (currently `v1` per the `hmac-sha256-v1=...` header
   prefix). Institutional ops teams reviewing the pack pre-
   integration use this field to confirm they are reading
   documentation for the signature version their incoming webhooks
   will use. The helper code does not read this field at runtime —
   webhook signature versions are carried in the signature header
   itself.

5. **`checksums.sha256` over every file in the pack.** SHA-256 is
   the algorithm; the format is the standard `<hex>  <relative
   path>` form that `sha256sum -c` consumes. Build pipeline
   computes the file, includes it in the tarball, and emits a
   second `<tarball>.sha256` for the tarball itself.

6. **Integrity now, authenticity deferred to Part 11.** The
   `checksums.sha256` provides *integrity* (tamper detection). It
   does NOT provide *authenticity* (proof that the publisher made
   this pack). GitHub releases lend authenticity through GitHub's
   own auth chain, but the authenticity property does not transit
   if the pack is mirrored elsewhere. SLSA provenance attestation
   plus Sigstore cosign signatures are the production-grade
   upgrade path and are deferred to Part 11 alongside the OCI
   distribution decision. This gap is documented here so it is
   visible at v0.1, not surprising at v0.2.

7. **Pre-flight blocker for public publication, not for build.**
   WBG legal sign-off on the actual license value is a blocker
   before the tarball is attached to a public GitHub release.
   Pack builds, ships internally, and is downloadable from the
   repository without this blocker; the blocker applies to the
   `gh release create` step only.

## Precedent

[docs/research/market-comparators.md §5.A.D](../research/market-comparators.md#5ad-standards-pack-distribution-and-provenance-added-prompt-9-for-adr-0039)
is the load-bearing reference.

The GitHub release tarball is the convergent regulator-domain
default. Open Banking UK's [read-write-api-specs](https://github.com/OpenBankingUK/read-write-api-specs)
publishes tagged releases per version with attached artifacts.
Brazil Open Finance's [github.com/OpenBanking-Brasil](https://github.com/OpenBanking-Brasil)
repositories follow the same pattern. Australian CDR's Standards
repository uses the same tagged-release model. The pattern is
auditable (git history shows what changed), versioned (semver from
v0.1.0 onward), and publicly downloadable.

The manifest field set with `portal_url` and a signature-version
declaration follows Open Banking UK's metadata patterns for
similar purposes.

The error catalog kept as markdown (`error-catalog.md`) not
converted to YAML follows Brazil Open Finance's pattern — markdown
is more readable for compliance staff reviewing the catalog pre-
integration than a YAML serialization.

The SLSA + cosign upgrade path follows the post-2024 regulator-
domain shift: Open Banking UK's pre-2024 releases did not have SLSA
attestations; the post-2024 releases do.

## Divergence

We diverge from OCI artifact distribution at v0.1. The GitHub
release tarball is the comparator-set default for v0.x; OCI is the
v1.0 / production target documented for Part 11.

We diverge from PyPI / npm publication of the SDK helpers at v0.1.
The pack carries them; public registry publication is a v1.0
commitment (see [ADR 0038](0038-sdk-helper-scope-and-distribution.md)).

We diverge from a final license selection. The `LicenseRef-`
placeholder is the SPDX-conforming way to publish a manifest
honestly while legal review is in flight. The placeholder name
explicitly names the gap ("sandbox-pending-legal-review") rather
than hiding it under an Apache-2.0 or proprietary guess.

We diverge from SLSA attestation at v0.1. The gap is named in the
Consequences section; the upgrade path is Part 11. Doing SLSA at
v0.1 would require setting up the attestation tooling, the cosign
key management, and the verification documentation for institutions
— all valuable, all explicitly out of v0.1 scope.

We diverge from a separate `event_type` or `webhook_event_schema`
field in the manifest. The pack ships one event type (batch
completion); the field is not needed yet. Reintroduce when agent events
diversify the event-type set (Prompt 12+).

## Consequences

- Institutions download via `gh release download` or browser-based
  file download from the GitHub release page.
  `checksums.sha256` lets them verify integrity. The
  `manifest.schema.json` in the pack lets them validate the
  manifest programmatically.

- Semver discipline starts at v0.1.0. v0.2.0 is the post-sprint
  release with conformance suite + Bruno collections + sandbox
  onboarding flow + WBG-legal-cleared license + SLSA attestation
  + OCI distribution.

- Breaking changes to the OpenAPI spec between pack versions are
  surfaced in release notes. The `api_server_compatibility`
  field's `exclusive_max_version` lets institutions detect when a
  pack is incompatible with a deployed API version.

- The integrity-vs-authenticity gap is named but not closed. An
  attacker who can publish a tarball with matching checksums to a
  mirror site can imitate the pack. GitHub's auth chain mitigates
  this for the official release page; the gap re-opens at any
  mirror. Closing it requires the Part 11 SLSA work.

- The license placeholder is an explicit blocker for public
  GitHub release. Internal distribution (the repository itself,
  internal mirrors) is unblocked. Operators reading the manifest
  see the placeholder and know that final license selection is
  pending.

- The pack-build script reuses the cleaned (post-A) OpenAPI spec
  and the SDK helpers from `sdk-helpers/`. A single source of
  truth principle: the pack is a snapshot of the repository, not
  a parallel hand-edited artifact.

- CI validates the pack on every PR. A pack that does not
  schema-validate, whose checksums do not match, or whose example
  payloads do not validate against the Pydantic models, fails
  the build.
