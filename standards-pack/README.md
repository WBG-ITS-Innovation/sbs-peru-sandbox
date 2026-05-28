# SBS SupTech Standards Pack v0.1

This directory is the **source** of the standards pack — the bundle
institutional integrators download to start an integration with the
SBS SupTech Complaints API. The `scripts/build-standards-pack.sh`
script populates the subdirectories from authoritative sources
elsewhere in the repository and produces the distributable tarball
`dist/standards-pack-v0.2.0.tar.gz` with a `.sha256` companion.

See [ADR 0039](../docs/adr/0039-standards-pack-v0-1-distribution-and-manifest.md)
for the distribution and manifest decisions and
[ADR 0038](../docs/adr/0038-sdk-helper-scope-and-distribution.md) for
the helper-vs-generator scope.

## What's in the pack

```
standards-pack/
├── manifest.json         provenance + version metadata
├── manifest.schema.json  JSON Schema for manifest.json (validate yourself)
├── README.md             this file
├── openapi/
│   └── sbs-complaints-v0.1.yaml  the canonical OpenAPI 3.1 spec, frozen at the pack's git commit
├── schemas/              JSON Schemas exported from the Pydantic models
│   ├── BatchManifest.json
│   ├── Complaint.json
│   ├── ProblemDetail.json
│   └── …
├── catalogs/
│   └── error-catalog.md  human-readable error code catalog
├── sdk-helpers/
│   ├── python/           hand-maintained Python webhook helper (pure stdlib)
│   └── typescript/       hand-maintained TypeScript helper (dual ESM+CJS)
├── examples/
│   ├── valid-anexo-1a-complaint.json
│   ├── valid-batch-manifest.json
│   └── invalid-missing-field.json   with expected ProblemDetail response
├── recipes/
│   ├── openapi-generator-java.md
│   ├── openapi-generator-csharp-netcore.md
│   ├── openapi-generator-go.md
│   ├── webhook-verification-java.md     ~30-line reference snippet
│   ├── webhook-verification-go.md       ~30-line reference snippet
│   ├── webhook-verification-python.md   pointer to sdk-helpers/python/README.md
│   └── webhook-verification-typescript.md  pointer to sdk-helpers/typescript/README.md
└── checksums.sha256      SHA-256 of every file in the pack
```

## How to verify the pack

```bash
# Verify the tarball:
sha256sum -c standards-pack-v0.2.0.tar.gz.sha256

# Extract and verify every file:
tar -xzf standards-pack-v0.2.0.tar.gz
cd standards-pack/
sha256sum -c checksums.sha256

# Validate the manifest against its schema:
jq -e . manifest.json > /dev/null         # well-formed JSON
ajv validate -s manifest.schema.json -d manifest.json  # if you have ajv
```

## How to use the pack

1. Read `openapi/sbs-complaints-v0.1.yaml` to understand the API
   contract. The portal at the URL in `manifest.json#portal_url`
   renders the same spec interactively.

2. Read `catalogs/error-catalog.md` to understand the error codes
   you must handle. Each entry names the HTTP status, the stable
   `code`, the `type` URI, and what to do on the client side.

3. If you integrate in Python or TypeScript, install the matching
   helper from `sdk-helpers/`. Each helper has a README with usage
   examples and CI-verified canonical-request agreement.

**Note on the in-pack TypeScript helper:** The `sdk-helpers/typescript/`
directory inside this pack is source reference. The full standalone
package tree (tests, build scripts, jest config) lives at
`sdk-helpers/typescript/` in the [project repository](https://github.com/WBG-ITS-Innovation/sbs-peru-sandbox).
Institutions who want the complete test harness should clone or
download the repo source rather than relying on the pack's contents
alone.

4. If you integrate in Java, .NET (csharp-netcore), or Go:
   - Use the OpenAPI Generator recipe at `recipes/openapi-generator-
     <lang>.md` to generate client code from `openapi/sbs-complaints-
     v0.1.yaml`. Pin the generator to `v7.10.0` and follow the "wrap,
     never edit generated files" pattern.
   - Use the reference webhook-verification snippet at
     `recipes/webhook-verification-<lang>.md` (Java, Go) to implement
     signature verification.

5. Validate your test payloads against the JSON Schemas in
   `schemas/`. The schemas are exported from the same Pydantic
   models the server uses for inbound validation, so any payload
   that matches the schema will not be rejected for shape reasons.

6. Check `examples/` for known-good and known-bad payloads. The
   `invalid-missing-field.json` example includes the expected
   ProblemDetail response so you can verify your error-handling
   path locally.

## Versioning and compatibility

`manifest.json#api_server_compatibility` declares the server-version
range this pack supports. The pack does not transit a server-version
check itself; comparing a pack version to a server-version is the
integrator's responsibility.

Semver discipline:

- Patch versions (`0.1.0` → `0.1.1`) fix bugs, clarify documentation,
  or correct example payloads. Wire-compatible.
- Minor versions (`0.1` → `0.2`) add fields or operations. Backward-
  compatible at the wire level; integrators may need to widen their
  client code to consume new fields.
- Major versions (`0.x` → `1.0`, `1.x` → `2.0`) signal breaking changes.
  The migration path is documented in the release notes.

v0.2 lands with conformance suite + Bruno/Postman collections +
sandbox onboarding flow + WBG-legal-cleared license + SLSA
attestation + OCI distribution.

## License

`manifest.json#license` declares
`LicenseRef-sandbox-pending-legal-review` at v0.1, an SPDX-conforming
placeholder while WBG legal review is in flight. The final license
(Apache-2.0, regulator-publication-public-domain, or other) lands in
v0.2.

This placeholder is a **pre-flight blocker for public GitHub release
publication** — the pack builds and ships internally without
clearing legal, but the `gh release create` step waits on legal
sign-off.
