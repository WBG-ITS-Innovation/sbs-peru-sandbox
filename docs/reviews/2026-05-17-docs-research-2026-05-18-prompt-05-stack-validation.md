# Cross-model review — docs-research-2026-05-18-prompt-05-stack-validation

- **Date:** 2026-05-17
- **Model:** gpt-5.4
- **Target:** docs-research-2026-05-18-prompt-05-stack-validation

---

## Summary

This note is mostly careful and usable. It makes clear what is a locked decision elsewhere and what is only a validation check for Prompt 5. The overall conclusion — proceed with caveats — is reasonable.

I looked for four things:

1. whether the choices match current standards,
2. whether the note overstates precedent,
3. whether any caveat affects the stated north-star principles,
4. whether any operational or governance risk is missing.

Main points:

- **OpenAPI 3.1 + JSON Schema 2020-12** is a sound choice for a regulator API. No disagreement on the core decision.
- **RFC 9457 problem details** is also a sound choice, but the note understates one implementation risk: if `type` URIs are published as placeholders and then changed later, institutions may treat them as stable identifiers. That is a compatibility issue, not just a naming clean-up issue.
- **Pydantic v2** is acceptable as an implementation detail, but the note is too quick to dismiss long-term portability concerns. If the project commits generated schemas from Pydantic and uses those as published artifacts, the implementation layer is no longer purely private. Differences in schema emission become part of the public surface unless there is a clear normalization step.
- **Stoplight Elements via unpkg CDN** is the weakest part against the project’s own principles. It conflicts with:
  - **one-command deploy**,
  - **observability as a first-class feature**,
  - and partly **product-grade onboarding**.
  The note treats this as a Prompt 9 concern, but the file itself says the portal artifact lives at `api/devportal/index.html`. Once that file is committed as part of the API surface, the delivery method matters now, not only later.

Substantive gap in the note: it does not discuss **version pinning and reproducibility** for the documentation renderer and schema export path. “8.x via unpkg CDN” is not a repeatable deployment input for a regulator-grade platform.

## Disagreements with primary review

1. **The Stoplight CDN caveat is too lightly treated**
   The note says, in section E, that CDN dependency is acceptable because “the dev portal in this prompt is for the development workstation only.” I do not agree with that framing.

   Why:
   - The stack inventory lists `api/devportal/index.html` as part of the repository artifact.
   - The project principle is one-command deploy. A dev portal that depends on third-party runtime asset fetching is not self-contained.
   - In regulated environments, outbound egress restrictions are common. Even on a developer workstation, this creates a non-deterministic onboarding path.

   What is missing:
   - exact version pinning for the JS and CSS asset URLs,
   - SRI hashes,
   - a vendoring plan or static-build fallback,
   - confirmation that the portal works with no Internet access.

2. **The Pydantic section understates public-surface coupling**
   Section B says the validation library “does not bind institutions” because OpenAPI is canonical. That is only partly true.

   If `model_json_schema()` output is committed to `api/openapi/schemas/*.json` and published as a separately consumable artifact, then:
   - Pydantic’s schema emission behavior,
   - field title/default/example formatting,
   - `$defs` layout,
   - and some validation keyword choices

   become visible to integrators unless normalized.

   Section C acknowledges cosmetic differences between OpenAPI and Pydantic schema output, but the review should go further: **a published schema export needs a documented canonicalization rule**. Otherwise the project can drift into “configuration over code” in name only, while tool-specific output details quietly define the interface.

3. **The RFC 9457 placeholder namespace is more serious than written**
   Section D says SBS must confirm the namespace before any institution integrates. That is right, but the note still rates the choice “Yes” for production-readiness. I would phrase this more narrowly: **yes, provided the namespace is fixed before any external publication or test onboarding**.

   In practice, institutions often key retry logic, dashboards, and support playbooks on stable problem `type` values. Changing from `https://sbs.gob.pe/errors/{code}` placeholder semantics later is a breaking change in operational terms even if payload shape is unchanged.

4. **The note does not test its own “benchmark precedent” standard consistently**
   The file is honest about citation gaps, which is good. But some precedent language is still too generous:
   - “Stoplight Elements is the most widely-used ‘Scalar-or-equivalent’” is asserted without evidence in this file.
   - “Swagger UI 3.1 support has lagged” may be true in broad terms, but needs either a dated qualifier or a citation if used to justify rejection.
   - “Scalar ... less production-tested at regulator scale” is also an assertion without comparator support.

   For a regulator-grade research note, where direct evidence is absent, it is better to say “no direct regulator comparator found” than to rank vendors from memory.

## Risks not flagged elsewhere

1. **Supply-chain and change-control risk for `unpkg` delivery**
   File reference: section E, “Stoplight Elements 8.x via unpkg CDN”.

   Risk:
   - “8.x” is a floating major range, not a pinned asset.
   - CDN-served browser assets can change outside repo control.
   - This weakens reproducibility, auditability, and incident investigation.

   Why it matters:
   - If documentation rendering changes after a dependency-side release, the repo state alone will not explain what users saw.
   - This is especially relevant for onboarding and support disputes.

   Expected control:
   - pin exact versions in asset URLs,
   - add SRI,
   - or vendor static assets.

2. **No explicit line between canonical OpenAPI and derived JSON Schema artifacts**
   File references: section A and section C.

   Risk:
   - The note says OpenAPI is canonical, but also says standalone JSON Schemas are separately published artifacts.
   - If there is any mismatch, institutions may treat the schema files as equally authoritative.
   - The note mentions `tests/test_openapi_pydantic_match.py`, but does not define what happens when there is disagreement.

   Missing policy:
   - Which artifact wins?
   - Is publication blocked on mismatch?
   - Are schema files generated only from the canonical OpenAPI, or from Python models, or both?

   Industry practice:
   - Mature API programs usually define one contract source of truth and generate other views from it, or enforce strict release-gate parity. This is common in gov.uk API programmes and large-bank OpenAPI governance models.

3. **No mention of RFC 9457 extension member policy**
   File reference: section D.

   Risk:
   - Problem Details almost always need extension members such as trace IDs, request IDs, field-level violations, support codes, or retry hints.
   - The note only mentions a `ProblemDetail` model matching required RFC fields.
   - Without a policy for extension members, teams later add ad hoc fields and break consistency.

   What should be decided now:
   - whether `instance` will carry request correlation,
   - whether field validation errors use an extension array,
   - whether `trace_id` or equivalent is mandatory,
   - whether extensions are stable and documented in `error-catalog.md`.

   Comparator examples:
   - Zalando REST guidelines,
   - HMRC error models,
   - Microsoft API guidelines,
   all define structured error extensions rather than relying on free text alone.

4. **No compatibility policy for schema evolution**
   File references: whole note, especially sections A–C.

   Risk:
   - The file validates tool choices but says nothing about compatibility rules for future changes:
     - adding enum values,
     - tightening regexes,
     - changing `required`,
     - changing numeric ranges,
     - altering `oneOf`/`anyOf` shapes.

   Why it matters:
   - For an institution-facing API, compatibility policy matters as much as format choice.
   - OpenAPI 3.1 and JSON Schema 2020-12 are flexible enough to allow both safe and breaking changes. The standard alone does not protect consumers.

   Missing artifact:
   - a short compatibility matrix in the ADR or contribution guide.

5. **Potential mismatch between OpenAPI examples and executable validation**
   File reference: section C discussion of cosmetic differences and semantic alignment tests.

   Risk:
   - The note mentions examples placement differences, but does not say whether examples are validated in CI.
   - In regulator APIs, stale examples are a common onboarding failure mode.

   Missing control:
   - CI should validate all examples against both the OpenAPI schema and the published standalone JSON Schema, or explicitly choose one canonical validation target.

6. **Renderer fallback is named, but switch criteria are not**
   File references: Summary caveat 1; sections A and E.

   Risk:
   - “Redoc 2.x is the documented fallback” is not enough.
   - Without defined acceptance criteria, a rendering defect may be discovered late and trigger an ad hoc tool switch.

   Missing detail:
   - what exact Stoplight failure conditions trigger fallback,
   - who decides,
   - whether both renderers are exercised in CI or preview,
   - whether screenshots or smoke tests are captured.

7. **No mention of localization / plain-language duty in error content**
   File reference: section D.

   Risk:
   - The project principle includes plain-language explainability.
   - The note validates the transport standard for errors, but not the content standard.
   - For SBS, Spanish-language operator support and institution-facing clarity likely matter.

   Missing policy:
   - whether `title` and `detail` are Spanish, English, or bilingual,
   - whether `type` docs will carry the plain-language explanation,
   - whether field names in validation errors mirror legal form labels or internal model names.

## Recommended actions

1. **Tighten the docs portal delivery plan now**
   - Replace “Stoplight Elements 8.x via unpkg CDN” with one of:
     - exact pinned CDN URLs plus SRI hashes, or
     - vendored static assets in-repo.
   - Add a short note stating whether `api/devportal/index.html` must render without Internet access.
   - If this is truly development-only, say so in the file header and exclude it from any deploy artifact path.

2. **Define the contract source of truth explicitly**
   Add one paragraph to this note or ADR 0027 covering:
   - canonical source: `api/openapi/sbs-api-v1.yaml`,
   - status of `api/openapi/schemas/*.json`: derived convenience artifacts,
   - release rule: any semantic mismatch blocks merge,
   - precedence rule: OpenAPI wins if tooling differs.

3. **Add a schema canonicalization step**
   If standalone JSON Schemas continue to come from Pydantic:
   - document the allowed transformations,
   - normalize ordering and metadata where possible,
   - and record which keywords are accepted as tool-specific noise.

   This should be tied to `tests/test_openapi_pydantic_match.py`, which the note already cites.

4. **Promote the RFC 9457 namespace issue from caveat to release gate**
   Before any external sandbox use:
   - confirm the final `type` URI namespace,
   - confirm whether those URIs dereference to human-readable docs,
   - and state whether the URI itself, the code inside it, or both are the stable identifier.

5. **Document Problem Details extensions now**
   Add to `api/openapi/error-catalog.md` and the note:
   - correlation field strategy,
   - field-level validation error format,
   - retryability indicator if used,
   - and localization rules for `title` and `detail`.

6. **Reduce unsupported vendor-comparison claims**
   In section E:
   - replace unsupported claims such as “most widely-used” or “less production-tested at regulator scale” with narrower wording,
   - or add sources.
   The same applies to any claims about Swagger UI lag unless a dated source is cited.

7. **Add a compatibility policy note**
   A half-page is enough. Cover:
   - what counts as breaking for OpenAPI and JSON Schema,
   - enum expansion policy,
   - required-field policy,
   - date/time format tightening policy,
   - error-code stability policy.

8. **Validate examples in CI**
   If not already present, add CI checks that:
   - every example payload in OpenAPI and docs validates,
   - every problem detail example matches the declared model,
   - and renderer smoke tests at least confirm the portal loads and the spec parses.

## Triage

_TODO: human-filled. Disposition each finding above as accept / defer / reject, with reason._

---

## Triage (filled 2026-05-18)

| Finding | Disposition | Notes |
| --- | --- | --- |
| 1. Stoplight CDN floating version | **ACCEPT — fixed in PR** | SRI hashes added; dev-only header added to `api/devportal/index.html`. |
| 2. Pydantic public-surface coupling | **DEFER to Prompt 6** | Canonicalisation policy documented when FastAPI scaffold lands. |
| 3. RFC 9457 namespace as release gate | **ACCEPT — promoted** | Now logged as explicit release gate in open-questions §5. |
| 4. Unsupported vendor comparisons | **DEFER to docs cleanup PR** | Wording polish; not contract-affecting. |
| Risk 1 — supply-chain on unpkg | **ACCEPT — fixed in PR** | Pinned 8.4.10 + SRI. |
| Risk 2 — canonical vs derived schema precedence | **ACCEPT — already in ADR 0027** | Reiterate in Prompt 6. |
| Risk 3 — ProblemDetail extension policy | **DEFER to Prompt 9** | Error catalog completion. |
| Risk 4 — compatibility policy | **DEFER to Prompt 9 / ADR 0013** | Standards Pack distribution work. |
| Risk 5 — examples validation in CI | **DEFER to Prompt 6** | Lands with the test infrastructure expansion. |
| Risk 6 — renderer fallback switch criteria | **DEFER to Prompt 9** | Portal completion. |
| Risk 7 — error-content localisation | **DEFER to SBS review** | Policy decision, not technical. |
