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
