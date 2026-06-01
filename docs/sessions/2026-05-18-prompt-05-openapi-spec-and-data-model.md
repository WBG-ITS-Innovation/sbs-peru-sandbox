# Session journal — 2026-05-18 — openapi-spec-and-data-model

- **Date:** 2026-05-18
- **Prompt:** 5
- **Part:** 2
- **Slug:** openapi-spec-and-data-model
- **Files touched (43):**
  - .spectral.yaml (new)
  - CLAUDE.md
  - api/devportal/index.html (new)
  - api/openapi/error-catalog.md (new)
  - api/openapi/sbs-api-v1.yaml (new)
  - api/openapi/schemas/BatchManifest.json (new)
  - api/openapi/schemas/BatchResultRow.json (new)
  - api/openapi/schemas/BatchResultsResponse.json (new)
  - api/openapi/schemas/BatchStatus.json (new)
  - api/openapi/schemas/BatchSubmission.json (new)
  - api/openapi/schemas/Complaint.json (new)
  - api/openapi/schemas/ComplaintCreated.json (new)
  - api/openapi/schemas/ComplaintListItem.json (new)
  - api/openapi/schemas/ComplaintListResponse.json (new)
  - api/openapi/schemas/ComplaintQuery.json (new)
  - api/openapi/schemas/ComplaintStatusPatch.json (new)
  - api/openapi/schemas/ComplaintSubmission.json (new)
  - api/openapi/schemas/HealthStatus.json (new)
  - api/openapi/schemas/InstitutionStatus.json (new)
  - api/openapi/schemas/ProblemDetail.json (new)
  - api/openapi/schemas/VersionInfo.json (new)
  - api/pyproject.toml
  - api/sbs_api/__init__.py (new)
  - api/sbs_api/models/__init__.py (new)
  - api/sbs_api/models/anexo_1a.py (new)
  - api/sbs_api/models/export_schemas.py (new)
  - api/sbs_api/models/requests.py (new)
  - api/sbs_api/models/responses.py (new)
  - docs/CONTRIBUTING.md
  - docs/DECISIONS.md
  - docs/PLAN.md
  - docs/adr/0026-anexo-1a-curated-subset.md (new)
  - docs/adr/0027-openapi-as-canonical-contract.md (new)
  - docs/adr/README.md
  - docs/research/2026-05-18-prompt-05-stack-validation.md (new)
  - docs/research/market-comparators.md
  - docs/reviews/2026-05-18-prompt-05-stack-validation.md (new)
  - docs/sessions/2026-05-18-prompt-05-open-questions.md (new)
  - scripts/regenerate-schemas.sh (new)
  - scripts/serve-devportal.sh (new)
  - tests/conftest.py
  - tests/test_anexo_1a_taxonomy.py (new)
  - tests/test_openapi_pydantic_match.py (new)
  - tests/test_pydantic_models.py (new)
  - uv.lock

## Cross-model review — triage line

SKIPPED: TLS cert path unresolved (SSL_CERT_FILE not set on the developer workstation; the corporate Azure OpenAI tenancy is reached through a TLS-intercepting proxy and requires the corporate CA bundle). Recorded in `docs/sessions/2026-05-18-prompt-05-open-questions.md` §1.1 for follow-up. Both the Workstream 0 mid-prompt cross-review and the closeout cross-review were skipped; the Workstream 0 note carries an inline adversarial reading substituting for the external pass. The closeout cross-review skip-reason placeholder is at `docs/reviews/2026-05-18-prompt-05-stack-validation.md` and a fresh closeout placeholder at `docs/reviews/2026-05-18-prompt-05-openapi-spec-and-data-model.md`.

## Adversarial review

Run via the `second-opinion` subagent on the staged diff.

**Headline finding.** The `ComplaintStatusPatch` model documented a "reason required on terminal status transition" rule in three places — its docstring, the `reason` field description, and a stub `_reason_present_on_terminal_states` field-validator that explicitly commented "the cross-field rule is enforced by a model_validator below" — but no model_validator existed. The helper method `reason_required()` was never called. The error catalog at `api/openapi/error-catalog.md` published `SBS-422-002 — Cross-field rule failed` as a stable error code citing this exact rule as its example. Result: a contract that promised something the code did not enforce, before the PR was even merged.

**Fixed in this same PR.** A `@model_validator(mode="after")` is now on `ComplaintStatusPatch` enforcing the rule (reason required, ≥10 non-whitespace characters, when `resolution_status ∈ {atendido, anulado}`). The OpenAPI spec at `api/openapi/sbs-api-v1.yaml` gained a JSON Schema 2020-12 `allOf` / `if-then` conditional so codegen tools surface the rule to client developers. The error catalog row for SBS-422-002 is amended to enumerate the two rules it currently triggers on (original_reference_id != complaint_id; reason on terminal transition). Seven new tests in `tests/test_pydantic_models.py` cover the rule across both terminal states, whitespace-only reasons, valid reasons, and the optional case on `pendiente`. Total test count: 148.

## What landed

Prompt 5 produces the foundation that every subsequent product prompt depends on: an OpenAPI 3.1 specification at `api/openapi/sbs-api-v1.yaml` defining nine endpoints across Tier 1 ingestion, Tier 2 batch, institution status, and metadata; Pydantic v2 data models implementing a 15-field subset of the Anexo 1-A complaint taxonomy from Resolución SBS N° 04036-2022 (reconciled against the resolución text); JSON Schemas exported from the Pydantic models and committed under `api/openapi/schemas/`; an error catalog of 23 stable error codes paired with RFC 9457 type URIs; and a developer portal that renders the OpenAPI document via Stoplight Elements at `http://localhost:8080/devportal/`. The work also produces a Workstream 0 stack-validation research note that confirms OpenAPI 3.1, Pydantic v2, JSON Schema 2020-12, RFC 9457, and Stoplight Elements as production-grade choices for this audience, with three caveats recorded in the open-questions file for the maintainer's review. No FastAPI scaffold, no database, no security primitives — those land in Prompts 6 and 7 per the May 25 critical path.

## Decisions locked

- **ADR 0026 — Anexo 1-A curated subset.** The May 25 sandbox carries a 15-field subset of Anexo 1-A; PII fields and full Anexo A/B/C code lists deferred to Part 11.
- **ADR 0027 — OpenAPI as canonical contract.** `api/openapi/sbs-api-v1.yaml` is canonical; Pydantic v2 implements it; JSON Schemas exported from Pydantic; the match-test in `tests/test_openapi_pydantic_match.py` enforces alignment.
- **Stoplight Elements (CDN) chosen for the developer portal**, with Redoc 2.x as the documented fallback. Logged in DECISIONS.md.

## Decisions deferred (to a named future prompt / part)

- Full Anexo 1-A field coverage (the remaining 8 of 23 fields + the four PII-bearing fields) — Part 11.
- Full Anexo A/B/C/D code-list distribution — Part 11.
- OpenAPI versioning policy with breaking-change procedure — Prompt 9 / Part 7.
- Per-language SDK generation from OpenAPI (.NET, Java, Python, TypeScript) — Part 7 (post-May 25).
- Conformance test suite — Part 7 (post-May 25).
- RFC 9457 `type` URI namespace under sbs.gob.pe — needs SBS sign-off (placeholder until then). Tracked in open-questions §2.
- Vendoring Stoplight Elements (or Redoc) into the repo — Prompt 9.
- FastAPI scaffold, /health triad, structlog + OTel — Prompt 6.
- mTLS, OAuth client_credentials, HMAC signing, idempotency middleware — Prompt 7.

## Decisions flagged for cross-model review

- The 15-field subset choice (vs full Anexo 1-A or vs a different curated cut). Owner: maintainer. Model: GPT-5 via Azure OpenAI (queued post-TLS fix).
- OpenAPI as canonical contract (vs Pydantic-first generated). Owner: maintainer. Model: GPT-5.
- Stoplight Elements vs Redoc choice for the demo. Owner: maintainer. Model: GPT-5.
- Whether `severity`, `description_language`, and `complainant_age_range` belong on the institution-submitted payload at all, given they have no Anexo 1-A counterpart. Owner: Sergio (compliance lead). Model: GPT-5.

## Subagent verdicts

- benchmark-checker (Workstream 0 note): APPROVE — all five stack choices anchored to specific §5.A sections with named comparators; two §5.A addenda (RFC 9457 + portal rendering) landed in this PR closed the citation gaps the note self-identified.
- reviewer: APPROVE WITH NITS — only flagged that `__all__` in `models/__init__.py` omitted `ComplaintListResponse` and `BatchResultsResponse`. Fixed in this PR.
- architect-guard: APPROVE WITH AMENDMENT — locked decisions (Python 3.12 / FastAPI / Pydantic v2 / SQLAlchemy 2.0 / mTLS+OAuth+HMAC+idempotency+RFC 9457+/v1 versioning) preserved; ADR 0025 May 25 scope untouched; ADRs 0026 and 0027 land Accepted with Precedent and Divergence sections present.
- doc-sync: APPROVE — every cross-reference required by the prompt spec is present (CLAUDE.md pointer, CONTRIBUTING.md subsection, ADR index rows, PLAN.md Part 2 updates, DECISIONS.md entries, market-comparators.md §5.A addenda, research note, open-questions file, reviews skip-reason file, executable scripts, conftest.py path update, error-catalog cross-reference in the spec).
- regulator-readability: PASS — no banned phrasing; `near-real-time` is used correctly throughout; `sandbox` consistently used (no `pilot bank`); acronyms (mTLS, RFC 9457, OAuth, HMAC, INEI, AFP, COOPAC, OBIE, BIRD, DPM) are introduced with surrounding context.
- benchmark-checker (ADRs 0026/0027): APPROVE — all six citations name specific market-comparators.md sections (§2.1 CFPB, §2.3 FCA PS25/19, §4 ECB BIRD, §5.A standards-pack table, §5.A RFC 9457 addendum, §5.A portal-rendering addendum) with named comparators and supported claims.
- second-opinion: WEAKNESS-FLAGGED — `ComplaintStatusPatch` cross-field rule documented in three places but not enforced. Fixed in this PR (model_validator added, OpenAPI dependentSchemas/if-then added, seven tests added, error catalog row amended). See "Adversarial review" section above.

## Paste-ready block for the maintainer

> Prompt 5 closed. Branch: `part-02/openapi-spec-and-data-model`. PR: _to fill at PR-create time_. Locked: ADR 0026 (15-field Anexo 1-A subset) + ADR 0027 (OpenAPI as canonical contract). Deferred: full taxonomy (Part 11), SDK gen + conformance suite (Part 7), Stoplight vendoring (Prompt 9), FastAPI scaffold (Prompt 6), security primitives (Prompt 7). Flagged for cross-review: 15-field subset choice; OpenAPI-as-canonical pattern; Stoplight-vs-Redoc; severity / description_language / complainant_age_range divergences. Active Part: 2. Next prompt opens with: Prompt 6 — FastAPI scaffold + /health triad + Postgres baseline against this OpenAPI contract.

## Notes

- **Pre-flight fallbacks fired.** SSL_CERT_FILE unset → both cross-reviews skipped. Spectral missing globally → installed locally via `npm install --no-save @stoplight/spectral-cli` (available at `./node_modules/.bin/spectral`). Resolución found at `/Users/omakhlouk/Downloads/Res. 4036-2022 - Reglamento de Gestión de Reclamos y Requerimientos (Anexos)[61].pdf`; read via a temporary `pypdf` venv (poppler/`pdftotext` and Homebrew are not installed on this machine — likely an Anaconda/system-Python interception). All fallbacks enumerated in `docs/sessions/2026-05-18-prompt-05-open-questions.md` §1.
- **Test count.** Baseline before this prompt: 44. After this prompt: 148 (44 baseline + 42 pydantic-model + 48 OpenAPI/Pydantic match + 14 taxonomy). The seven additional tests over the original 141 cover the `ComplaintStatusPatch` cross-field rule surfaced by the adversarial review. `uv run pytest tests/` runs in ~0.2 seconds.
- **Spectral lint.** Clean — no errors at the `error` severity. Run via `./node_modules/.bin/spectral lint api/openapi/sbs-api-v1.yaml`. The configuration file `.spectral.yaml` extends `spectral:oas` with a small set of override rules.
- **Resolución reconciliation.** Anexo N° 1-A has 23 fields. The 15-field subset maps 12 fields to direct Anexo 1-A counterparts and three to prototype-level divergences with no Anexo 1-A counterpart (`severity`, `description_language`, `complainant_age_range`). The four PII-bearing Anexo 1-A fields (#3, #4, #5 — Número de documento, Nombre completo, Código de cliente) are deliberately excluded for the sandbox. Full reconciliation table in ADR 0026.
- **Developer portal render check.** `bash scripts/serve-devportal.sh`, then visit `http://localhost:8080/devportal/`. `curl` against the local server returned 200 with the rendered HTML and the OpenAPI YAML served from the same origin. Stoplight Elements 8.4.10 from unpkg.
- **Comparator file extension.** `docs/research/market-comparators.md` §5.A gained two short addenda — one on RFC 9457 adoption among regulator APIs (FCA/OBIE, European Commission, GOV.UK, HMRC), one on documentation portal rendering (Stoplight Elements vs Redoc vs Scalar). Both were promised by the Workstream 0 note and are referenced by ADR 0026 and ADR 0027.
- **What did not land.** No FastAPI scaffold. No database schema. No security primitives. No Tier 2 batch processing pipeline. No synthetic data generator. No getting-started guide. No Postman collection. No agents. No ML. No UI wiring. No CDN vendoring. No carry-over harness bug fixes. All per the scope-out section of the Prompt 5 spec.


---

## Post-closeout addendum (2026-05-18)

This addendum is appended after PR #25 was squash-merged to main as `6affcaa`. The sections above are the record of the unattended Prompt 5 run; this addendum records the follow-up cross-review work that landed on PR #26 (squash-merged as `5c95ec8`).

### Why an addendum and not an in-place edit

The journal above was written when the cross-reviews were skipped (TLS unresolved). Editing the original sections to retroactively claim the cross-reviews ran cleanly would lose the historical accuracy of the May 18 run. The addendum preserves the original record and tells future readers where to look for the final state.

### What changed

- **TLS configured.** Corporate TLS-decrypt root certs added to the trust bundle at `~/certs/corp-ca-bundle.pem`. `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` persisted in `~/.zshrc`. Detail in the open-questions addendum §5.1.
- **Both cross-reviews re-run and triaged.** `docs/reviews/2026-05-17-docs-research-2026-05-18-prompt-05-stack-validation.md` and `docs/reviews/2026-05-17-api-openapi-sbs-api-v1.md` both carry filled Triage sections.
- **Three contract bugs fixed.** OAuth scope mismatch (global default was `complaints.write`); `complainant_district` ubigeo length (`^\d{4}$` → `^\d{6}$` to match canonical INEI DDPPDD); PATCH `/status` response shape (`ComplaintCreated` → `Complaint`). All three are on PR #26.
- **Dev portal fixed.** Original `@stoplight/elements@8.4.10` was a non-existent version; both assets were unpkg error strings with identical bogus SRI hashes. Now pinned to `9.0.19` with two real distinct SRI hashes. Visually verified.
- **Polish.** `Location: format: uri` on 201; duplicate `security:` blocks on `/health` and `/version` consolidated.
- **18 secondary findings dispositioned** with explicit Prompt-N targets in the open-questions addendum §5.5.
- **5 standing risks** elevated for SBS review at May 25 (open-questions addendum §5.6).
- **RFC 9457 namespace** promoted from maintenance caveat to release gate (open-questions addendum §5.7).

### Test count update

148 → 151 passing. The three new tests cover the corrected ubigeo: canonical 6-digit acceptance, abroad sentinel `999999`, and 5-digit rejection. Spectral lint remains clean.

### Subagent verdicts on PR #26

Not re-run via the closeout pipeline (PR #26 was a focused remediation, not a closeout). The triage decisions in the two cross-review files plus the manual fix verification (151 tests + spectral clean + visual portal check) are the audit trail.

### Final state

- PR #25 → `6affcaa` (Prompt 5 original).
- PR #26 → `5c95ec8` (cross-review remediation).
- Two open-questions sections: §1–4 from the unattended run, §5 post-closeout addendum.
- Next prompt: Prompt 6 — FastAPI scaffold, `/health` triad, Postgres + pgvector, structlog + OTel, RFC 9457 middleware, Alembic baseline, against this canonical OpenAPI contract.
---

## Post-closeout addendum (2026-05-18)

This addendum is appended after PR #25 was squash-merged to main as `6affcaa`. The sections above are the record of the unattended Prompt 5 run; this addendum records the follow-up cross-review work that landed on PR #26 (squash-merged as `5c95ec8`).

### Why an addendum and not an in-place edit

The journal above was written when the cross-reviews were skipped (TLS unresolved). Editing the original sections to retroactively claim the cross-reviews ran cleanly would lose the historical accuracy of the May 18 run. The addendum preserves the original record and tells future readers where to look for the final state.

### What changed

- **TLS configured.** Corporate TLS-decrypt root certs added to the trust bundle at `~/certs/corp-ca-bundle.pem`. `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` persisted in `~/.zshrc`. Detail in the open-questions addendum §5.1.
- **Both cross-reviews re-run and triaged.** `docs/reviews/2026-05-17-docs-research-2026-05-18-prompt-05-stack-validation.md` and `docs/reviews/2026-05-17-api-openapi-sbs-api-v1.md` both carry filled Triage sections.
- **Three contract bugs fixed.** OAuth scope mismatch (global default was `complaints.write`); `complainant_district` ubigeo length (`^\d{4}$` → `^\d{6}$` to match canonical INEI DDPPDD); PATCH `/status` response shape (`ComplaintCreated` → `Complaint`). All three are on PR #26.
- **Dev portal fixed.** Original `@stoplight/elements@8.4.10` was a non-existent version; both assets were unpkg error strings with identical bogus SRI hashes. Now pinned to `9.0.19` with two real distinct SRI hashes. Visually verified.
- **Polish.** `Location: format: uri` on 201; duplicate `security:` blocks on `/health` and `/version` consolidated.
- **18 secondary findings dispositioned** with explicit Prompt-N targets in the open-questions addendum §5.5.
- **5 standing risks** elevated for SBS review at May 25 (open-questions addendum §5.6).
- **RFC 9457 namespace** promoted from maintenance caveat to release gate (open-questions addendum §5.7).

### Test count update

148 → 151 passing. The three new tests cover the corrected ubigeo: canonical 6-digit acceptance, abroad sentinel `999999`, and 5-digit rejection. Spectral lint remains clean.

### Subagent verdicts on PR #26

Not re-run via the closeout pipeline (PR #26 was a focused remediation, not a closeout). The triage decisions in the two cross-review files plus the manual fix verification (151 tests + spectral clean + visual portal check) are the audit trail.

### Final state

- PR #25 → `6affcaa` (Prompt 5 original).
- PR #26 → `5c95ec8` (cross-review remediation).
- Two open-questions sections: §1–4 from the unattended run, §5 post-closeout addendum.
- Next prompt: Prompt 6 — FastAPI scaffold, `/health` triad, Postgres + pgvector, structlog + OTel, RFC 9457 middleware, Alembic baseline, against this canonical OpenAPI contract.
