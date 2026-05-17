# Prompt 5 — open questions for the maintainer

This file enumerates everything that surfaced during the unattended Prompt 5 run that the maintainer should review at the typed approval gate before merging. None of these halted execution; they are flagged here so the human checkpoint at closeout is informed.

- **Date opened:** 2026-05-18
- **Run mode:** unattended
- **Owner of resolution:** maintainer (Othman)
- **Closeout gate:** read this file before typing the approval string for `/close-prompt --prompt 5`

---

## Section 1 — Pre-flight fallbacks that fired

### 1.1 SSL_CERT_FILE not set on the developer workstation

- **Observed.** `echo $SSL_CERT_FILE` returned empty. The cross-review pipeline (`scripts/cross_review.py`) routes through Azure OpenAI in the WBG ITS tenancy, which requires the WBG/Zscaler CA bundle to be trusted. Without `SSL_CERT_FILE` pointing at the WBG CA bundle, the Python `httpx`/`openai` client cannot validate the TLS chain against Azure.
- **Action taken in this run.** Both cross-reviews (the Workstream 0 mid-prompt cross-review on the stack-validation research note, and the closeout cross-review on the staged diff) were skipped using the `--skip-cross-review-with-reason "TLS cert path unresolved at <empty>, requires maintainer attention"` path. An inline adversarial reading of the research note is recorded inside the note itself in lieu of the external cross-review.
- **What the maintainer should do.** Set `SSL_CERT_FILE` (and, if needed, `REQUESTS_CA_BUNDLE`) to the WBG/Zscaler CA bundle path. The setup instructions are in `docs/setup/corporate-proxy-and-zscaler.md` (currently DRAFT). Once set, `/cross-review` on the closeout artifacts is a viable post-merge follow-up; alternatively, queue it as a Prompt 6 pre-flight item.

### 1.2 spectral was not on `PATH`

- **Observed.** `spectral --version` exited 127.
- **Action taken in this run.** A global install via `npm install -g @stoplight/spectral-cli` was rejected with EACCES on `/usr/local/lib`. A local install via `npm install --no-save @stoplight/spectral-cli` succeeded; spectral 6.16.0 is now available at `./node_modules/.bin/spectral`. Spectral lint of the OpenAPI specification ran from that path; results are recorded in the session journal.
- **What the maintainer should do.** Decide whether to (a) commit a `package.json`/`package-lock.json` for the spectral dependency so the install is reproducible across machines, (b) take a permissions-fix path to enable a real global install (`sudo chown -R $(whoami) /usr/local/lib/node_modules`), or (c) defer spectral to a CI-only check via a GitHub Actions step. Option (a) is cleanest; option (c) is most consistent with the "harness tooling lives in CI" pattern of Part 2.

### 1.3 Anexo 1-A reconciliation against Resolución SBS N° 04036-2022

- **Observed.** The resolución PDF was located at `/Users/omakhlouk/Downloads/Res. 4036-2022 - Reglamento de Gestión de Reclamos y Requerimientos (Anexos)[61].pdf` and read via a temporary `pypdf` virtualenv (poppler/`pdftotext` were not installed, and `brew` is not on this machine — Anaconda or system Python interception is suspected).
- **Action taken in this run.** Anexo N° 1-A has 23 fields in the resolución. The 15-field English subset chosen for May 25 has been reconciled against those 23 fields. The mapping is recorded in full in [ADR 0026](../adr/0026-anexo-1a-curated-subset.md) under "Field-by-field reconciliation".
- **What the maintainer should review (the divergences).**
  - **`severity`** has no counterpart in Anexo 1-A. It is a derived/internal supervisory triage field, not a regulator-mandated field on the regulated firm's record. It is included here because the agent layer (Part 5+) needs a severity signal in the request schema for the prototype; this is a *prototype* divergence, not a regulator-mandated one. Confirm with Sergio whether severity belongs on the institution-submitted payload or whether it should move to a separate supervisor-internal model.
  - **`description_language`** has no counterpart. It is included to handle Quechua/Aymara/English narratives — the resolución is silent on language tagging. Low risk; flag for completeness.
  - **`complainant_age_range`** has no counterpart. It is included as a bucketed proxy for complainant demographics that avoids storing raw date-of-birth (the resolución requires `Número de documento de identidad` as a PII field, which the prototype deliberately does *not* mirror). Confirm with Sergio whether age-range bucketing is acceptable in lieu of the resolución's PII fields for the May 25 sandbox, given the project's PII-minimisation posture.
  - **PII exclusions.** The resolución's PII-bearing fields (`Tipo de documento de identidad` #2, `Número de documento de identidad` #3, `Nombre completo del cliente` #4, `Código de cliente` #5) are *deliberately excluded* from the May 25 subset. The prototype is a sandbox that operates on synthetic data; the API contract is shaped around pseudonymous identifiers (`complaint_id`, `institution_id`, `original_reference_id`). Confirm this posture with the SBS reviewers — they may want a PII envelope shipped as a separate authenticated endpoint or a field set that production institutions must populate. This is a *policy* decision, not a *technical* one.

---

## Section 2 — Stack-level objections surfaced by Workstream 0

The Workstream 0 research note is [docs/research/2026-05-18-prompt-05-stack-validation.md](../research/2026-05-18-prompt-05-stack-validation.md). The aggregate verdict is **Proceed with caveats** for the reasons summarised below; each is detailed in the note's per-choice section and called out here for the maintainer's eye.

- **OpenAPI 3.1 vs 3.0 rendering compatibility.** OpenAPI 3.1 adopts JSON Schema 2020-12, which Stoplight Elements supports but with some known rendering quirks for `oneOf` discriminator union shapes. The dev portal renders cleanly on this spec; if a future contract change introduces a discriminated union, switch to Redoc 2.x as the documented fallback. No action needed unless that contingency triggers.
- **Pydantic v2 in regulator-domain production codebases.** No public regulator API has stated "we are on Pydantic v2" — most public regulator stacks are JVM (FCA, EBA, BCB internals) or .NET (CFPB internals are not public). The closest public Python-on-Pydantic-v2 fintech precedent is Stripe's openapi codegen toolchain (Pydantic v2 for client validation in their Python SDK). The note treats this as a low-risk divergence: Pydantic v2 is the mainstream Python validation library, and the OpenAPI spec is the canonical contract (per ADR 0027) so the choice of validation library is implementation-level, not contract-level.
- **RFC 9457 `type` URI namespace.** The spec uses `https://sbs.gob.pe/errors/{code}` as a placeholder namespace. The actual namespace requires SBS sign-off — they may want `https://api.sbs.gob.pe/errors/...` or a sub-path under an existing portal. Flag for the May 25 review.

---

## Section 3 — Schedule / scope notes

- **No new tests broke.** Baseline `uv run pytest tests/` was 44 passing before Workstream A. The new tests under `tests/test_pydantic_models.py`, `tests/test_openapi_pydantic_match.py`, `tests/test_anexo_1a_taxonomy.py` are additive — the closeout pipeline will report the new total.
- **No FastAPI scaffold landed.** Prompt 5 produces specification, models, schemas, and a docs portal. The HTTP layer lands in Prompt 6 per scope. If on closeout review the maintainer wants the `/health` triad in this same PR, that is a scope expansion — open a follow-up rather than re-opening Prompt 5.
- **No security primitives landed.** mTLS, HMAC, OAuth all land in Prompt 7 per scope.

---

## Section 4 — Things flagged but not yet a decision

- The closeout cross-review skip means the staged diff has not had a second-model adversarial pass. The internal `second-opinion` subagent run substitutes for it as far as Conventions allow, but if the closeout cross-review is important to the maintainer for this PR, the typed approval gate is the place to hold and re-run it once TLS is fixed.
- The `error-catalog.md` lists 23 stable error codes. Two are flagged inside the file as "needs SBS naming confirmation" (`SBS-401-005 mtls-cert-not-trusted` and `SBS-403-002 institution-not-onboarded`). Read the catalog before approval.
- The developer portal renders via Stoplight Elements 8.x (CDN). The CDN dependency is documented as a Prompt 9 vendoring concern; no action needed for this PR.
- The `second-opinion` adversarial subagent flagged that the `ComplaintStatusPatch` model documented a "reason required on terminal status transition" rule that was not actually enforced (the docstring promised a `model_validator` that did not exist; the error catalog row SBS-422-002 cited the rule as its example). **Fixed in this PR** by adding the `model_validator` to `ComplaintStatusPatch`, adding a JSON Schema 2020-12 `allOf` / `if-then` conditional to the OpenAPI spec so codegen tools surface the rule, and adding seven tests covering the rule (one for each terminal state, one for whitespace-only reason, one for happy path, plus the original optional-reason-on-pendiente case). The error catalog row for SBS-422-002 is amended to be specific about which two rules trigger it in v0.1.0.
