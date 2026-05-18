---
title: Stack validation — Prompt 5 (OpenAPI 3.1, Pydantic v2, JSON Schema, RFC 9457, Stoplight Elements)
date: 2026-05-18
source: Inline research synthesised against existing comparator files
status: Pre-build validation for Prompt 5; no aggregate decision is locked here — see Aggregate verdict and ADRs 0026/0027 for the locked outcome.
---

# Summary

Plain-language: the five technology choices that Prompt 5 inherited from prior planning — OpenAPI 3.1 for the contract, Pydantic v2 for request and response validation, JSON Schema 2020-12 as a separately-published artifact, RFC 9457 problem+json for error responses, and Stoplight Elements for the developer-portal rendering — are production-grade choices for an institution-facing regulator API, with three caveats the maintainer should see before the May 25 sprint:

1. OpenAPI 3.1 is the right specification version, but a small set of 3.1-only keywords (notably `oneOf` discriminator union shapes against JSON Schema 2020-12) have known rendering quirks in some Stoplight Elements builds. Redoc 2.x is the documented fallback if a future contract change trips the quirk.
2. Pydantic v2 is the mainstream Python validation library; no *public* regulator API has stated "we are on Pydantic v2", so the precedent is by indirect analogy rather than direct citation. Since the OpenAPI specification is the canonical contract (ADR 0027), the validation library is an implementation choice that does not bind institutions.
3. The RFC 9457 `type` URI namespace `https://sbs.gob.pe/errors/{code}` used in this spec is a placeholder. SBS must confirm the namespace before any institution integrates against it.

Aggregate verdict: **Proceed with caveats.** The caveats are tracked in `docs/sessions/2026-05-18-prompt-05-open-questions.md` for review at the closeout typed approval gate. None of them blocks Workstreams A–E from landing in Prompt 5.

# Stack inventory

| Choice | Version pin | Where it lives |
| --- | --- | --- |
| API specification format | OpenAPI 3.1.0 | `api/openapi/sbs-api-v1.yaml` |
| Python validation library | Pydantic v2 (`>=2.13`) | `api/sbs_api/models/` |
| Standalone schema export | JSON Schema 2020-12 via `model_json_schema()` | `api/openapi/schemas/*.json` |
| Error model | RFC 9457 problem+json | `api/openapi/error-catalog.md` and the `ProblemDetail` Pydantic model |
| Developer portal rendering | Stoplight Elements 9.0.19x via unpkg CDN | `api/devportal/index.html` |

# Per-choice verdict

## A. OpenAPI 3.1 as the canonical contract format

- **Decision.** OpenAPI 3.1.0, hand-curated, with Pydantic-exported JSON Schemas committed alongside.
- **Production-readiness verdict.** Yes.
- **Precedent.** Cited from [market-comparators.md §5.A](market-comparators.md#5a-api-and-schema-layer): "For the SBS sandbox, the reusable market pattern is: OpenAPI + JSON Schema + validation rules + versioned code lists + sample payloads." That section's "standards pack" table explicitly names OpenAPI specification as the first artifact a regulator should publish. The framing draws on CFPB ([§2.1](market-comparators.md#21-us-cfpb-consumer-complaint-database)), FCA ([§2.3](market-comparators.md#23-uk-fca-complaints-reporting-regime)), EBA DPM/XBRL governance ([§4](market-comparators.md#4-two-tier-regulatory-data-collection-precedents)), and HMRC's bridging-software tiering pattern. All four publish formal machine-readable contracts as their institution-facing surface.
- **Alternatives considered and rejection reason.**
  - *AsyncAPI* — relevant for the event-bus layer (Redis Streams emissions, webhook callbacks) and will be introduced in Part 4 or Part 6 for those surfaces. Not the right choice for the Tier 1 synchronous ingestion API. AsyncAPI does not replace OpenAPI for synchronous HTTP.
  - *GraphQL* — rejected because the institution-facing audience expects formal REST contracts. None of the comparator regulators use GraphQL. Tooling for code generation, conformance testing, and client SDKs in .NET/Java is materially weaker than for OpenAPI.
  - *JSON:API* — narrower than OpenAPI; would lock the response shape to JSON:API conventions and rule out form-multipart for Tier 2 batch upload.
  - *OpenAPI 3.0 instead of 3.1* — rejected because 3.1 adopts JSON Schema 2020-12 (one schema dialect across the spec and the exported standalone schemas), unifies nullable handling, and is now standard tooling. 3.0 is in maintenance mode.
- **Known production caveats.** A subset of Stoplight Elements builds have rendering quirks against 3.1's discriminator union shapes. Redoc 2.x renders 3.1 cleanly and is the documented fallback. The spec currently has no discriminator unions, so the quirk does not bite this PR.

## B. Pydantic v2 for request and response validation

- **Decision.** Pydantic v2 (`>=2.13`) for all request/response models; `model_json_schema()` for schema export.
- **Production-readiness verdict.** Yes with caveats.
- **Precedent.** No public regulator API publicly states "Pydantic v2 in production." Closest *Python-on-Pydantic* fintech precedent is Stripe's Python SDK, which uses Pydantic v2 in its generated client code; AWS Powertools for Python lambda also uses Pydantic v2 as its default validation backend. Both are production at scale. In the regulator domain, public stacks are usually JVM (FCA's DISP back-end stack, EBA reporting tooling) or .NET (CFPB internals are not public); the validation library is therefore non-comparable. The precedent for *validation as a separate layer behind the OpenAPI contract* is well-established — [market-comparators.md §5.A](market-comparators.md#5a-api-and-schema-layer) lists "validation rules" as a separate standards-pack artifact, distinct from the OpenAPI specification.
- **Alternatives considered and rejection reason.**
  - *marshmallow* — older, less integrated with OpenAPI generation, weaker type-hint integration. Heavy use in legacy Flask stacks; not the current Python ecosystem default.
  - *attrs + cattrs* — lighter, but no JSON-Schema export and no first-class FastAPI integration. Would require hand-written JSON-Schema generation, which is the precise burden ADR 0027 avoids by treating Pydantic as the JSON-Schema exporter.
  - *msgspec* — fastest in micro-benchmarks, but immature ecosystem and no first-class FastAPI integration. Reconsider in Part 9 if request-throughput becomes a bottleneck (it will not at sandbox load).
- **Known production caveats.** Pydantic v2's strict mode behaves slightly differently from v1 for date/time coercion; this is captured by per-field validators in `anexo_1a.py` rather than relying on default coercion.

## C. JSON Schema 2020-12 as a separately-published artifact

- **Decision.** Each Pydantic public model is exported to `api/openapi/schemas/<ModelName>.json` via `model_json_schema()` and committed. Institutions can validate payloads against these schemas without parsing the full OpenAPI document.
- **Production-readiness verdict.** Yes.
- **Precedent.** [market-comparators.md §5.A](market-comparators.md#5a-api-and-schema-layer) explicitly lists "JSON Schema" as the second artifact in the standards-pack table, separate from the OpenAPI specification. [§4](market-comparators.md#4-two-tier-regulatory-data-collection-precedents) cites EBA's Data Point Model with XBRL taxonomies and ECB's BIRD reporting dictionary — both treat the machine-readable schema as a publishable artifact in its own right, distinct from any HTTP API description. CFPB exposes complaint field references separately from its OData/JSON access endpoints.
- **Alternatives considered and rejection reason.**
  - *Embedded in OpenAPI only* — rejected because institutions integrating via batch Tier 2 do not need the OpenAPI; they need only the payload schema. Separate JSON Schemas reduce friction.
  - *XBRL taxonomy* — used by EBA. Out of scope for the May 25 sandbox; reconsider in Part 11 standards-pack work post-sprint, as documented in PLAN.md.
- **Known production caveats.** OpenAPI 3.1 inline schemas and Pydantic-exported standalone schemas are both JSON Schema 2020-12, but they differ in cosmetic details (`examples` placement, property ordering, `$defs` vs OpenAPI `components/schemas`). `tests/test_openapi_pydantic_match.py` enforces semantic alignment while tolerating cosmetic differences via a small allowlist.

## D. RFC 9457 problem+json for error responses

- **Decision.** Every error response uses the RFC 9457 problem+json media type, with stable `type` URIs under a placeholder namespace `https://sbs.gob.pe/errors/{code}` and a Pydantic `ProblemDetail` model that matches the RFC's required fields.
- **Production-readiness verdict.** Yes.
- **Precedent.** RFC 9457 (formerly RFC 7807) is the IETF standard for HTTP problem details. Adopted by:
  - FCA's API surface (the Open Banking Implementation Entity standards, which the FCA endorses, prescribe RFC 7807-style error responses; the OBIE standards predate the 9457 republication).
  - The European Commission's REST API guidelines.
  - GOV.UK's API design guidance.
  - HMRC's Making Tax Digital error model.
  None of these is in [market-comparators.md](market-comparators.md) yet. *Citation gap.* The most defensible move is to extend [market-comparators.md §5.A](market-comparators.md#5a-api-and-schema-layer) with a one-paragraph addendum on RFC 9457 adoption; this is folded into the closeout for this prompt.
- **Alternatives considered and rejection reason.**
  - *Custom error envelope* — rejected because every comparator-friendly approach is converging on a standard; inventing a custom envelope makes generated SDKs harder.
  - *Just an HTTP status with a string body* — rejected because the error catalog needs stable machine-readable identifiers for institutions to wire into retry/alert logic.
- **Known production caveats.** The `type` URI namespace is a placeholder until SBS confirms. The placeholder is marked clearly in the spec and the catalog file. Flagged in [docs/sessions/2026-05-18-prompt-05-open-questions.md](../sessions/2026-05-18-prompt-05-open-questions.md) §2 for SBS sign-off.

## E. Stoplight Elements for the developer portal rendering

- **Decision.** Stoplight Elements 9.0.19x loaded via the unpkg CDN, rendering `api/openapi/sbs-api-v1.yaml`. Self-contained HTML; no Node build step in the repo. Redoc 2.x is the documented fallback if a 3.1 keyword causes a rendering glitch.
- **Production-readiness verdict.** Yes with caveats.
- **Precedent.** PLAN.md Part 7 lists "Documentation portal (rendered from `docs/`; Scalar or equivalent for the OpenAPI surface)" — Stoplight Elements is the most widely-used "Scalar-or-equivalent." Direct comparator: FCA's developer portal renders an OpenAPI-derived view (proprietary skin over an OpenAPI document); CFPB's Developer portal renders an OAS document. *Citation gap on Stoplight specifically* — the comparator file does not name Stoplight by vendor. The note treats this as a tool choice rather than a regulator-domain decision; the regulator-domain decision is "render an OpenAPI document as a navigable docs portal", which is documented in [market-comparators.md §5.A](market-comparators.md#5a-api-and-schema-layer) and [§7](market-comparators.md#7-public-complaint-taxonomies-or-apis-sbs-can-borrow-from).
- **Alternatives considered and rejection reason.**
  - *Redoc 2.x* — equally good for rendering 3.1; chosen as the *fallback* rather than the primary because Stoplight Elements has better navigation for multi-tag specs, which this spec has (Ingestion, Batches, Institutions, Health).
  - *Swagger UI* — older project, 3.1 support has lagged. Rejected.
  - *Scalar* — newer project, strong UX, but smaller community and less production-tested at regulator scale. Reconsider for Part 7's full onboarding portal.
  - *Vendoring (npm-bundling Elements into the repo)* — out of scope for Prompt 5 per PLAN.md (Part 7 / Prompt 9 concern). Until then, CDN is the documented pattern.
- **Known production caveats.** CDN dependency on unpkg.com. Air-gapped or strict-egress institutional environments would require a vendored bundle; that is a Prompt 9 concern. The dev portal in this prompt is for the development workstation only.

# Aggregate verdict

**Proceed with caveats.** The five inherited stack choices are sound for the May 25 sprint and the institution-facing surface they produce. The caveats summarised in the Summary section above are not stoppers; they are matters for the maintainer's review at the closeout typed approval gate. The build moves forward to Workstreams A–E.

Mid-prompt cross-review of this note was skipped (TLS cert path unresolved; see [open-questions §1.1](../sessions/2026-05-18-prompt-05-open-questions.md#11-ssl_cert_file-not-set-on-the-developer-workstation)). An inline adversarial reading by the implementing session is below in lieu of the external second-model pass.

# Inline adversarial reading (substituting for the skipped mid-prompt cross-review)

The strongest objection to this note, as written, is that it treats the *absence of a public Pydantic-v2 regulator precedent* (per-choice section B) as a minor caveat. A more cautious reading would say: regulator APIs in production are overwhelmingly JVM- or .NET-backed because those stacks have a longer audit history; choosing a Python+Pydantic stack means SBS will be the only public-domain regulator API operating on that stack. The defence in section B is correct in principle — the OpenAPI spec is the contract, the validation library is implementation — but if the SBS reviewers prefer a JVM-tier validation library for production handoff, the entire `api/sbs_api/models/` layer would need replacement. That is a re-platforming risk, not a re-implementation risk, and it is not captured in the per-choice "Reconsider" verdict.

Resolution: this objection is recorded in the [open-questions](../sessions/2026-05-18-prompt-05-open-questions.md) file as a stack-level item for the maintainer to surface at the May 25 review. The Pydantic decision does not bind institutions (they generate clients from the OpenAPI spec) and is reversible without breaking the contract.

The second-strongest objection is that section D (RFC 9457) names four comparators *none of which are in market-comparators.md*. The note proposes folding a one-paragraph addendum into market-comparators.md in this same PR; that is the right move and is in the Workstream 0 deliverable list.

# Comparator-file extensions landed in this PR

Two extensions are landed in this PR to close the citation gaps identified above:

1. A one-paragraph addendum to [market-comparators.md §5.A](market-comparators.md#5a-api-and-schema-layer) on RFC 9457 adoption among regulator APIs (FCA/OBIE, European Commission, GOV.UK, HMRC).
2. A one-paragraph addendum to the same section noting that OpenAPI documentation rendering (Stoplight Elements / Redoc / Scalar) is a tooling choice downstream of the OpenAPI-as-canonical-contract decision.

The addenda are folded into [market-comparators.md](market-comparators.md) so future ADRs can cite them by section directly.
