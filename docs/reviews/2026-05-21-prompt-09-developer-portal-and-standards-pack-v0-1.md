# Cross-model review — tmp-prompt-09-full-diff

- **Date:** 2026-05-21
- **Model:** gpt-5.4
- **Target:** tmp-prompt-09-full-diff

---

## Summary

This change is useful and mostly well-structured. The main decisions are documented, the tests are broader than usual for this stage, and the one-command path is present (`make standards-pack`, `scripts/demo.sh`). I did not find a fundamental design error in the portal route, helper scope, or standards-pack direction.

I did find several gaps that matter for a regulator-grade platform:

1. **The public contract is incomplete because the portal routes are hidden from the generated OpenAPI schema.**
   In `api/openapi/sbs-api-v1.yaml` the routes `/portal/` and `/portal/assets/{filename}` are documented, but the FastAPI handlers set `include_in_schema=False` in `api/sbs_api/routes/portal.py:78-81` and `api/sbs_api/routes/portal.py:96-99`. If the served `/v1/openapi.yaml` is repository-curated and not generated from handlers, this may be intentional, but it creates a drift hazard: runtime routing and documented surface can diverge without framework-level detection.

2. **The portal HTML response lacks cache and validator headers, despite this being called out as deferred.**
   `api/sbs_api/routes/portal.py:83-93` returns raw `HTMLResponse` with no `Cache-Control`, `ETag`, or `Last-Modified`. For a static vendored page, this is an unnecessary inefficiency and weakens observability during change rollout because clients cannot reliably validate freshness. The session journal already notes this as deferred; I agree it is still a real gap.

3. **The standards-pack build mutates tracked workspace state in place.**
   `scripts/build-standards-pack.sh:57-80` deletes and repopulates `standards-pack/*` inside the working tree, then creates `dist/...`. This matches the current `.gitignore`, but it is still fragile: local untracked edits under `standards-pack/openapi`, `schemas`, `examples`, etc. are destroyed, and the build is not isolated. For “one-command deploy” and auditability, an out-of-tree build directory is safer.

4. **The manifest schema requires `attestation`, but the schema’s top-level `required` list omits it.**
   `standards-pack/manifest.schema.json:6-18` does not require `attestation`, while later `properties.attestation` describes it as required. The build script always writes it (`scripts/build-standards-pack.sh:141-161`), and tests assert it (`tests/test_standards_pack_build.py:202-216`), but the schema does not enforce it. That is a real contract bug.

5. **The OpenAPI Generator recipe test does not do what its docstring claims.**
   `tests/test_openapi_generator_recipes.py` only checks markdown contents. The workflow `.github/workflows/standards-pack-validate.yml:68-91` does not actually invoke openapi-generator-cli or Docker either. This conflicts with the test file docstring and the session journal claim that recipe smoke tests run in CI. Right now there is no evidence in this patch that the generator commands are exercised.

6. **The demo replay script inserts directly into the live database and queue with hard-coded local endpoints.**
   `scripts/demo_replay.py:36-38` hard-codes `postgresql://sbs:sbs@localhost:5432/sbs_dev` and Redis localhost defaults. This is acceptable for a narrow demo tool, but it cuts against “configuration over code” and makes the script non-portable outside the author’s expected local stack. The README now promotes this script to integrators (`README.md:73-80`), so the assumptions should be explicit and configurable.

## Disagreements with primary review

I disagree with any review that treats the following as “minor nits”:

1. **Schema omission for `attestation` is not a nit.**
   `standards-pack/manifest.schema.json:6-18` failing to require `attestation` weakens the published artifact contract. The ADR says the field exists so the authenticity gap is visible at the artifact boundary. If the schema does not require it, that guarantee is not true.

2. **The claimed CI coverage for OpenAPI Generator recipes is overstated.**
   The test file says full invocation lives in the workflow, but the workflow shown does not run it. That is not a documentation nit; it is a false assurance problem. In a regulated setting, claimed controls need to match actual controls.

3. **In-place build mutation deserves more scrutiny.**
   `scripts/build-standards-pack.sh` deletes and rewrites large parts of `standards-pack/`. That is convenient, but it is not clean build isolation. For a regulator-facing release artifact, I would not wave this through as harmless.

4. **Hard-coded demo infrastructure values are a platform concern, not just a demo concern.**
   Once `README.md` tells institutional users to run `scripts/demo.sh`, the script becomes part of onboarding surface. `scripts/demo_replay.py:36-38` and `scripts/demo.sh:101-117` should not assume one fixed local topology without configuration hooks.

## Risks not flagged elsewhere

1. **Portal route documentation can silently drift from runtime behavior.**
   Because handlers are excluded from schema generation (`api/sbs_api/routes/portal.py:78-81`, `96-99`) while the YAML is maintained separately (`api/openapi/sbs-api-v1.yaml:568-637`), there is no framework-backed check that route parameters, response codes, or content types still match. This is a known trade-off when using curated specs, but then you need explicit contract tests for these routes against the YAML. I do not see that here.

2. **`/portal/assets/{filename}` OpenAPI response content is structurally awkward.**
   `api/openapi/sbs-api-v1.yaml:613-621` lists three content types under one `200` response for one path parameter constrained by enum. Many client generators handle this poorly, especially when the same status code has multiple primitive string content entries. Since this is a public route, it may be acceptable, but if the route is mainly for browsers, documenting it in OpenAPI at all may add more generator noise than value.

3. **The build depends on platform-specific tools without preflight checks.**
   `scripts/build-standards-pack.sh` uses `shasum`, `tar`, `gzip`, `find`, `xargs`, `sed`, `awk`, `date`, and `uv`. It only preflights `git` (`scripts/build-standards-pack.sh:40`). On some Linux images `shasum` is absent while `sha256sum` exists; on minimal environments `uv` may be absent even if Python is present. The GitHub workflow likely masks this, but the local maintainer path is not truly hermetic.

4. **The standards-pack tarball name is version-pinned in multiple places.**
   I counted repeated `0.1.0` and `standards-pack-v0.1.0.tar.gz` assumptions in:
   - `Makefile:18,43`
   - `README.md:58-61`
   - `.github/workflows/standards-pack-validate.yml:77-88`
   - `scripts/build-standards-pack.sh:26-35`
   - `tests/test_standards_pack_build.py:48-49`
   This will create avoidable release churn and partial upgrades. Version bumps should come from one source of truth.

5. **The Python packaging metadata uses placeholder URLs that are not clearly internal-only.**
   `sdk-helpers/python/pyproject.toml:29-30` sets `Documentation` and `Repository` to `https://example.invalid/...`. This is better than fake real domains, but if the helper is installed from the pack and inspected by tooling, these URLs are not useful. Since publication is deferred, either omit them or point to the in-repo paths.

6. **The TypeScript package files included in the standards pack are not enough to run `npm test` from the extracted pack.**
   The build copies `package.json`, tsconfigs, `jest.config.js`, and `index.ts` (`scripts/build-standards-pack.sh:107-116`) but not the `tests/` directory or the helper build scripts under `sdk-helpers/typescript/scripts/`. The README implies the helper is a usable distribution surface. For TypeScript, the extracted pack is incomplete as a standalone package source tree.

7. **`assert` is used for invariant enforcement in application code.**
   `api/sbs_api/routes/portal.py:53-56` uses `assert` to enforce allowlist/media-type map alignment. Running Python with optimizations (`-O`) removes asserts. For startup invariants in application code, an explicit runtime check that raises `RuntimeError` is safer.

8. **The demo output path is always under ignored `tmp/`, with no retention or cleanup policy.**
   `scripts/demo.sh:123-128` writes to `tmp/demo-run/<timestamp>/`. For repeated demos on shared machines or CI runners, this will accumulate logs and generated data. Not a blocker, but worth a cleanup flag or retention note.

## Recommended actions

1. **Make `attestation` required in the manifest schema.**
   Update `standards-pack/manifest.schema.json` top-level `required` list to include `"attestation"`. This is the clearest correctness fix in the patch.

2. **Add a real CI smoke test for the OpenAPI Generator recipes, or remove the claim that it exists.**
   Best path:
   - add a workflow step that runs the documented Docker commands for Java, Go, and csharp-netcore against `standards-pack/openapi/sbs-complaints-v0.1.yaml`
   - assert expected output files exist
   If Docker-in-Docker is not wanted, then rewrite `tests/test_openapi_generator_recipes.py` docstring and session notes to match reality.

3. **Replace the `assert` in `portal.py` with an explicit check.**
   In `api/sbs_api/routes/portal.py:53-56`, use:
   ```python
   if set(VENDOR_ASSET_MEDIA_TYPES) != set(VENDOR_ASSET_ALLOWLIST):
       raise RuntimeError(...)
   ```
   This preserves the invariant under optimized Python runs.

4. **Add cache and validator headers for the portal HTML.**
   In `api/sbs_api/routes/portal.py:83-93`, add at least:
   - `Cache-Control: no-cache` or short max-age with revalidation
   - `ETag` derived from file bytes or git commit
   - optionally `Last-Modified` from file mtime
   This is standard practice for static HTML entrypoints. GitHub Pages, nginx, and common ASGI static serving setups all do some form of this.

5. **Move standards-pack build output to a temporary staging directory, then sync into final artifact form.**
   Build under something like `tmp/build/standards-pack/` or `dist/build/standards-pack/`, validate there, then tar from there. If you still want `standards-pack/` as a visible tree, make that a deliberate export step, not the build workspace itself.

6. **Parameterize demo infrastructure settings.**
   In `scripts/demo_replay.py`, make DSN, Redis host/port, and storage dir configurable via flags or environment variables with current values as defaults. At minimum:
   - `--dsn`
   - `--redis-host`
   - `--redis-port`
   - `--storage-dir`

7. **Create one source of truth for pack version and filenames.**
   Put version in one file or Make variable and have:
   - build script
   - workflow artifact name
   - tests
   - README examples
   read from it. This will reduce release mistakes.

8. **Decide whether the TypeScript helper inside the pack is meant to be runnable as-is.**
   If yes, copy:
   - `sdk-helpers/typescript/tests/`
   - `sdk-helpers/typescript/scripts/rename-cjs-to-cjs.js`
   - `sdk-helpers/typescript/scripts/rename-esm-to-mjs.js`
   into the pack.
   If no, say clearly in `standards-pack/README.md` that the TypeScript helper is source reference, not a full standalone package tree.

9. **Add a route/spec conformance test for the portal endpoints.**
   Since the spec is curated and handlers are excluded from framework schema generation, add a focused test that checks the runtime route table and key response behavior against the documented YAML entries for `/portal/` and `/portal/assets/{filename}`.

10. **Expand build preflight checks for local reproducibility.**
    In `scripts/build-standards-pack.sh`, preflight `uv`, `shasum`, and a supported `tar` flavor. Fail early with clear instructions.


## Triage

- **#1 Make `attestation` required in the manifest schema** — **accept, fixed in this commit**. Real contract bug. ADR 0039 claims the field guarantees authenticity-gap visibility at the artifact boundary; the schema now enforces that claim by listing `attestation` in the top-level `required` array.
- **#2 Real CI smoke test for OpenAPI Generator recipes** — **defer to v0.2**. Current recipe tests verify markdown content (version pinning, wrap-don't-edit pattern, csharp-netcore not csharp). Full Docker-based generator invocation adds Docker-in-Docker complexity to the workflow; lands with conformance suite in v0.2.
- **#3 Replace `assert` with explicit `RuntimeError` in portal.py** — **accept, fixed in this commit**. Three-line fix; application invariants no longer depend on `-O` being off.
- **#4 Cache and validator headers for portal HTML** — **defer to v0.2**. Already in v0.2 carry-forward list. Asset routes have immutable cache headers; HTML headers are a separate concern.
- **#5 Out-of-tree build for standards-pack** — **defer to v0.2**. `.gitignore` covers generated content; acceptable for sandbox v0.1. Cleaner isolation lands with OCI distribution decision in Part 11.
- **#6 Parameterize demo infrastructure settings** — **defer to v0.2**. demo.sh is sprint-demo scaffolding; institutional integrators use the helpers and OpenAPI spec, not `demo_replay.py` directly. v0.2 cleanup with Part 8 admin path.
- **#7 Single source of truth for pack version** — **defer to v0.2**. Real release-hygiene concern; lands alongside semver discipline in v0.2.
- **#8 TypeScript helper completeness in pack** — **accept, fixed in this commit**. Added clarifying note to `standards-pack/README.md` that the in-pack TypeScript helper is source reference; full standalone tree lives at `sdk-helpers/typescript/` in the project repo. Cheaper than copying the test tree into the pack.
- **#9 Route/spec conformance test for portal endpoints** — **defer to v0.2**. Curated-spec drift is real; lands alongside the conformance test suite in v0.2.
- **#10 Expanded build preflight checks** — **defer to v0.2**. CI workflow currently masks platform-specific gaps; lands with out-of-tree build (#5).

**Summary: 3 accept-now fixes applied in this commit, 7 deferred to v0.2 with rationale on each. No rejects — all findings are valid.**
