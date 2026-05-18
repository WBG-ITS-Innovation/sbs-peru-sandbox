# SBS SupTech Prototype — Build Plan

**Scope:** Full multi-agent SupTech platform with regulator-grade API, MCP+A2A+LangGraph three-layer architecture, on-prem deployment, vendor-handoff-ready.

**Structure:** 10 parts. Move to next part when exit criteria met.

## North Star

A reference implementation that:
- Ingests complaints via regulator-grade API (Tier 1 real-time + Tier 2 batch)
- Routes through multi-agent analytics (5 specialist agents)
- Surfaces findings via dual-lens dashboards + agent workspace
- Deployable by vendor onto SBS on-prem via Helm
- Adapts to other regions via configuration

## Locked architectural decisions

- Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 async, Alembic, arq
- DB: PostgreSQL 16 + pgvector
- Event bus: Redis Streams (behind EventBus interface)
- ML: BETO/RoBERTa-BNE via ONNX, XGBoost+SHAP, MLflow
- Agents: LangGraph internal, A2A inter-agent, MCP for tools
- LLM: vLLM serving Qwen 2.5 14B Instruct, on-prem
- Frontend: Next.js 14 App Router, TypeScript, Tailwind, shadcn/ui, Recharts, TanStack Query
- Infra: Docker Compose (dev), Helm chart (deploy), Terraform modules
- Observability: OpenTelemetry + Prometheus + Grafana + Loki
- API: mTLS + OAuth client_credentials + HMAC signing + idempotency + RFC 9457 + /v1 path versioning

## Vertical slice target (end of Part 4)

A signed mTLS request to `POST /v1/complaints` → validated against Annex 1-A → persisted → event emitted → audit log → trace in Grafana. End-to-end, observable, repeatable.

## May 25 sprint kickoff critical path

The May 25 sprint kickoff in Lima is the next milestone. The audience is the SBS policy and technical reviewers and the WBG delivery team. (Named attendees are kept in meeting notes, not in this plan.)

The 11-Part scope is the July deliverable, not the May 25 deliverable. This section documents the May 25 critical path: the 13-prompt sequence from Prompt 1 through May 25, of which Prompts 1-3 are already closed and Prompts 4-13 remain, the per-Part scope (full / reduced / deferred), and the target dates for deferred work. See [ADR 0025](adr/0025-may-25-sprint-critical-path.md) for full rationale.

### The 13-prompt sequence

- Prompts 1-3: closed. Workflow harness, supply chain & secrets, uv project + Python tooling.
- Prompt 4: May 25 scope-lock and PLAN.md restructure. *This document.*
- Prompt 5: ruff + pyright + pre-commit hardening + Prompt 3 carry-over fixes (writer/reader contract on `## Triage`, silent `--slug` fallback, deploy-test `.gitkeep` false positive).
- Prompts 6-7: OpenAPI 3.1 spec + Pydantic v2 models + JSON Schema export; FastAPI scaffold + Tier 1 endpoints + Postgres + RFC 9457 problem+json.
- Prompt 8: mTLS + HMAC + OAuth client_credentials.
- Prompt 9: Tier 2 batch + synthetic data generator (10k complaints, 3 scenarios, deterministic seeds).
- Prompts 10-11: UI wiring against the real API + pretrained BETO classifier (Spanish, no fine-tuning).
- Prompts 12-13: two agents live (pattern detection + supervisory query authoring) + (stretch) three more.
- Day 9 (May 25 morning): rehearsal + standards pack v0.1 generated and version-stamped + brief k6 load test.

### Per-Part May 25 scope

Each Part's May 25 scope is documented in a "May 25 scope" subsection under that Part below. Deferred items name a target date (June or July post-sprint) and the follow-up Part that owns them.

### Schedule risk

If Prompts 9-13 slip, the demonstration runs against Prompts 5-8 alone: Tier 1 near-real-time ingestion (signed and authenticated, RFC 9457, idempotency) end-to-end, preserving the minimum observable chain from the vertical slice target — a signed mTLS request to `POST /v1/complaints` → validated against Annex 1-A → persisted → event emitted → audit log → trace in Grafana. Tier 2 batch upload and the synthetic data generator are framed as the post-sprint roadmap. The UI shows the Tier 1 ingestion path; bulk-load and historical backfill come post-sprint. The pretrained BETO classifier (Part 5 reduced scope) and the two live agents (Part 6 reduced scope) are also deferred to the post-sprint roadmap under this fallback; the UI shows the architecture story for these surfaces without live behaviour. This is a thinner fallback than the full demonstration and the audience expectation is calibrated to it in advance, not at the demo. If any of Prompts 5-8 itself slips, the demonstration loses the signed-ingestion floor entirely; in that case the maintainer escalates to the WBG tech lead and the WBG manager before May 25 to either compress remaining prompts, reduce Prompts 5-8 scope, or shift the demonstration to an architecture-walkthrough format. That escalation is the load-bearing risk control for the critical path. See [ADR 0025 Consequences](adr/0025-may-25-sprint-critical-path.md#consequences).

## The 10 parts

### Part 1 — Foundation

Progress so far (updated 2026-05-17 after Prompts 1 and 2 merged). Use `[~]` for partial completion with a note; `[ ]` is untouched; `[x]` is done.

- [x] Repo + uv project initialized — uv workspace, root `pyproject.toml`, `.python-version` pinned to 3.12, `uv.lock` committed (Prompt 3). See [ADR 0021](adr/0021-package-manager-uv.md), [ADR 0022](adr/0022-python-version-3-12.md), [ADR 0023](adr/0023-workspace-layout-uv-members.md).
- [~] Tooling: ruff, pyright strict, pre-commit, gitleaks, conventional commits, spectral — `pre-commit`, `gitleaks` (binary via CI), Conventional Commits (pre-push hook + CLAUDE.md) ✓; `ruff`, `pyright strict`, `spectral` land in Prompt 4.
- [x] Project structure: api/, agents/, tools/, frontend/, infra/, docs/, scripts/, sdk/ — all directories present (Prompt 3). `api/`, `agents/`, `tools/`, `sdk/` are uv workspace members with stub `pyproject.toml`; `frontend/` and `infra/` are `.gitkeep` placeholders for Parts 8 and 9.
- [ ] Docker Compose: Postgres+pgvector, Redis, vLLM (Qwen 2.5 14B), Prometheus, Grafana, Loki, OTel collector
- [ ] OTel collector configured, Grafana provisioned
- [~] CI: lint + test + type-check on PR — `secret-scan` workflow (gitleaks binary, history-aware) ✓; lint/test/type-check workflows land with the tooling in Prompt 4.
- [ ] ADR 0001 written: MCP+A2A+LangGraph three-layer — deferred to Prompt 9 per Prompt 1 session journal.

**Additionally landed in Prompts 1–2 that the original Part 1 checklist did not enumerate:**

- [x] Workflow harness: six subagents, eight slash commands, closeout pipeline with typed approval gate (Prompt 1).
- [x] Supply-chain controls: secret scanning (`.pre-commit-config.yaml` + CI `secret-scan.yml`), `.gitleaks.toml` allowlist, `.secrets.baseline`, Dependabot (3 ecosystems, grouped), `.env` handling policy. (Prompt 2)
- [x] ADRs 0015–0020 Accepted (cross-review backend, scanner stack, dependency tooling, SBOM format, dependency-review threshold, env handling).
- [x] Two research files under `docs/research/`: regulator-domain (`market-comparators.md`) and operational supply-chain (`supply-chain-precedents.md`).
- [x] Deferred-work tracker (`docs/DEFERRED.md`) and PR template, CODEOWNERS, issue templates.

**Exit:** `docker compose up` clean, CI green

### Part 2 — Data Model & API Skeleton
- [~] config/taxonomies/sbs-peru-v1.yaml — full Annex 1-A — Prompt 5 ships a 15-field subset in code; YAML taxonomy file deferred to Part 11 (full code-list distribution).
- [x] Pydantic v2 models — Prompt 5 (api/sbs_api/models/) for the 15-field subset. See [ADR 0026](adr/0026-anexo-1a-curated-subset.md).
- [x] OpenAPI 3.1 specification — Prompt 5 (api/openapi/sbs-api-v1.yaml). Hand-curated; canonical contract. See [ADR 0027](adr/0027-openapi-as-canonical-contract.md).
- [x] JSON Schema export from Pydantic — Prompt 5 (api/openapi/schemas/). Regenerate via `bash scripts/regenerate-schemas.sh`.
- [x] Developer portal — Prompt 5 (api/devportal/index.html via Stoplight Elements CDN). Run with `bash scripts/serve-devportal.sh`.
- [x] RFC 9457 problem+json error model + error catalog — Prompt 5 (api/openapi/error-catalog.md, ProblemDetail model).
- [x] Alembic baseline migration (all tables defined) — Prompt 6 (api/migrations/versions/20260518_0001_baseline.py).
- [x] FastAPI with /health, /health/ready, /health/live — Prompt 6. Three probes with explicit semantics per [ADR 0030](adr/0030-health-probe-semantics.md); a fourth `/health/startup` was added.
- [x] structlog + OTel tracing on every endpoint — Prompt 6. structlog binds `trace_id` / `span_id` / `correlation_id`; OTel owns trace context per [ADR 0028](adr/0028-fastapi-application-structure.md) §4-5.
- [x] GET /v1/complaints returns empty list with proper headers — Prompt 6. The endpoint is live and authenticated via the auth-stub dependency (Prompt 7 replaces with real auth).
- [ ] ADR 0002: Taxonomy as configuration — Part 11.
- [ ] Second opinion: Template 6 (OpenAPI review) — GPT-5 — queued for post-Prompt 5 once TLS to Azure OpenAI is configured (see open-questions §1.1).

**Exit:** Scalar docs render, trace visible in Grafana. **Part 2 closed at Prompt 6 (2026-05-18).** Exit demonstration: `bash scripts/smoke-test.sh` runs against a locally-running API and exercises the behavioral contract (ETag round-trip, idempotency replay, tenant binding, state machine, ProblemDetail, body size limit). Grafana trace visibility lands with the observability stack in Part 9; the OTel SDK is wired and the `traceparent` header is on every response so the stack swap-in is mechanical.

**May 25 scope.** Full. OpenAPI 3.1 spec, Pydantic v2 models (Prompt 5 ships the 15-field subset; full taxonomy is Part 11), Alembic baseline (Prompt 6), FastAPI scaffold with `/health` triad (Prompt 6), Scalar docs site (replaced by Stoplight Elements per [ADR 0027](adr/0027-openapi-as-canonical-contract.md) and the stack-validation note), structured logging and OTel tracing (Prompt 6). `GET /v1/complaints` returns empty list with proper headers (Prompt 6). No reductions. See [ADR 0025](adr/0025-may-25-sprint-critical-path.md).

### Part 3 — Ingestion Tier 1
- [ ] mTLS termination + dev CA scripted
- [ ] OAuth 2.0 client_credentials flow
- [ ] HMAC-SHA256 request signing middleware
- [ ] Idempotency-Key handling (24h cache)
- [ ] Per-client rate limiting (Redis)
- [ ] RFC 9457 problem+json errors with stable codes
- [ ] POST /v1/complaints with full validation
- [ ] Event emission to Redis Streams
- [ ] Audit log on every state-changing operation
- [ ] Python reference SDK started
- [ ] ADR 0003: API authentication
- [ ] ADR 0004: Error model RFC 9457
- [ ] Build code review agent v1 (GitHub Action)
- [ ] Second opinion: Template 3 (security) — GPT-5
- [ ] Second opinion: Template 2 (library verification) — GPT-5

**Exit:** signed mTLS request → 201 → event → audit log → trace

**May 25 scope.** Full. Near-real-time API endpoint accepting complaint submissions mapped to the Annex 1-A taxonomy. mTLS termination, OAuth 2.0 client_credentials, HMAC request signing, idempotency keys, RFC 9457 problem+json error model. No reductions. See [ADR 0025](adr/0025-may-25-sprint-critical-path.md).

### Part 4 — Ingestion Tier 2 + Synthetic Data
- [ ] POST /v1/batches (signed multipart)
- [ ] Async batch processing (arq)
- [ ] Shared validation pipeline (same code as Tier 1)
- [ ] Webhook callbacks (HMAC signed)
- [ ] Synthetic data generator: 10k complaints, 3 scenarios
- [ ] scripts/demo.sh replay-scenario
- [ ] ADR 0005: Synthetic data strategy
- [ ] Build spec-drift agent v1
- [ ] Second opinion: Template 1 (scenarios realism) — Gemini 2.5 Pro

**Exit:** VERTICAL SLICE — Tier 1 + Tier 2 end-to-end. Loom recording for safekeeping.

**May 25 scope.** Full. Tier 2 batch file upload mapped to the same Annex 1-A taxonomy. Synthetic complaint generator (10k complaints, 3 scenarios, deterministic seeds) replaces real production data for the sandbox. **Slip-case: this Part is the largest single risk to the demonstration; under the Prompts-5-8 fallback it becomes post-sprint roadmap. Cut line if Tier 2 slips: ship Tier 1 only with an explicit "Tier 2 batch deferred to post-sprint" card in the demo deck.** See [ADR 0025](adr/0025-may-25-sprint-critical-path.md).

### Part 5 — ML Substrate
- [ ] BETO classification worker (ONNX export)
- [ ] pgvector embeddings worker
- [ ] XGBoost ranker + SHAP
- [ ] MLflow registry with all models
- [ ] MCP tool servers: classify_complaint, embed_text, vector_search_complaints, rank_priority, explain_ranking, query_complaints, get_taxonomy, cite_regulation
- [ ] ADR 0006: ML serving + MCP exposure
- [ ] Second opinion: Template 2 (MCP SDK verification) — GPT-5
- [ ] Second opinion: Template 5 (mid-build architecture review) — Gemini 2.5 Pro

**Exit:** new complaint classified, embedded, ranked within seconds; all MCP tools tested

**May 25 scope.** Reduced. Pretrained BETO classifier only (Spanish, no fine-tuning), demonstrating the classifier interface against synthetic complaints. **Deferred to post-sprint (July):** BETO fine-tuning on SBS historical data, XGBoost ranker, SHAP explainer, MLflow registry, full ML pipeline. The classifier contract is documented in an ADR; the full ML pipeline lands in July. See [ADR 0025](adr/0025-may-25-sprint-critical-path.md).

### Part 6 — Agent Infrastructure
- [ ] A2A server scaffolding per specialist agent
- [ ] Agent Cards at /.well-known/agent.json
- [ ] LangGraph state schemas
- [ ] Case file model
- [ ] Approval queue state machine (proposed→reviewed→approved/rejected→executed→notified)
- [ ] Orchestrator service (A2A client)
- [ ] Triage Agent end-to-end (proof of architecture)
- [ ] ADR 0007: A2A inter-agent protocol
- [ ] ADR 0008: Case file design
- [ ] ADR 0009: Human-in-the-loop state machine
- [ ] Second opinion: Template 1 (case file design) — GPT-5
- [ ] Second opinion: Template 2 (A2A SDK verification) — GPT-5

**Exit:** Triage Agent processes complaint event end-to-end, A2A+MCP calls in traces

**May 25 scope.** Reduced. Two agents live: pattern detection and supervisory query authoring. Three agents (institutional risk, conduct, investigation) ship pre-generated output. All five named and described in the UI; the three pre-generated agents render archived output. The three pre-generated agents render output that is generated by the same agent code path running against curated synthetic complaints in advance, not hand-written prose; the demonstration can show the generation command and the output file together. Architecture documents how the three pre-generated agents are wired. Stretch goal: all five live by end of Day 8. **Deferred to post-sprint (June):** three pre-generated agents go live. See [ADR 0025](adr/0025-may-25-sprint-critical-path.md).

## Plan restructure — 2026-05-15

The plan was extended from 10 to 11 Parts. The earlier Parts 7–10 (Specialist Agents I/II, Frontend, Polish/Deploy/Handoff/Demo) are reorganised into the new structure below:

- Specialist Agents (Pattern, Institutional Risk, Conduct, Investigation) extend the agent infrastructure from Part 6 and are scheduled across follow-up prompts that build on Part 6's scaffolding.
- Frontend work (Agent Workspace, Approval Queue, dashboards) is now part of Part 8 (Self-Service Onboarding + Per-Institution Ops), framed around the regulator user flows rather than a demo deliverable.
- Helm / Terraform / runbook / SBS handoff work is now Part 9 (Production Readiness).
- Demo polish moves into Part 9's exit criteria.

This is a re-scoping, not a de-scoping. Nothing is abandoned; the framing shifts from "demo at end" to "regulator-grade reference handoff".

### Part 7 — Developer Portal + Onboarding Tier A

Goal: an institution's integration team can self-onboard against a sandbox using documentation, generated SDKs, and a conformance test suite — without a kick-off call.

- [ ] Documentation portal (rendered from `docs/`; Scalar or equivalent for the OpenAPI surface).
- [ ] Sandbox environment formalised (config-driven, isolated from the regulator's prod surface).
- [ ] SDK generation via `openapi-generator` for **.NET**, **Java**, **Python**, **TypeScript**. Published packages with semantic versioning.
- [ ] Conformance test suite — a third party can run the suite against any deployment to prove their integration is correct.
- [ ] Postman + Bruno collections committed and kept in sync with the OpenAPI spec.
- [ ] Getting-started guide: zero-to-first-signed-request in ≤30 minutes from cold.
- [ ] Onboarding runbook for SBS staff: how to issue a sandbox credential, rotate it, revoke it.
- [ ] ADR for SDK distribution and versioning policy.
- [ ] Plain-language onboarding overview readable by Veronica.
- [ ] Second-opinion review: onboarding flow vs CFPB and FCA developer portal precedents.

**Exit:** A fresh integration team can read the docs, generate an SDK, sign a request, hit the sandbox, and pass the conformance suite — without contacting SBS. Verified end-to-end on a clean machine.

**May 25 scope.** Minimal. Stoplight or Redoc rendering of the OpenAPI spec; OpenAPI + JSON Schema generated and version-stamped as the v0.1 standards pack (paired with Part 11 work). **Deferred to post-sprint (June/July):** SDK generation for .NET, Java, Python, TypeScript via `openapi-generator`; conformance test suite; getting-started guide; full onboarding portal. See [ADR 0025](adr/0025-may-25-sprint-critical-path.md).

### Part 8 — Self-Service Onboarding + Per-Institution Ops (Tier B)

Goal: SBS staff can onboard, monitor, and manage supervised institutions from the platform UI; supervised institutions can manage their own integration metadata.

- [ ] SBS-side onboarding UI: create institution, issue credentials, set per-institution config (rate limits, allowed scopes, taxonomy version).
- [ ] Institution-side self-service: rotate credentials, view their own ingestion metrics, see their conformance status.
- [ ] Per-institution observability: dashboards showing ingestion volume, validation error rates, signing errors, latency percentiles by institution.
- [ ] Per-institution audit log surfaced in the UI.
- [ ] Agent Workspace + Approval Queue + Radar dashboard + Alarm dashboard, all wired to per-institution scope.
- [ ] EN/ES localisation across all UI strings.
- [ ] Plain-language operations guide readable by Sergio.
- [ ] ADR for the multi-tenancy and credential model.
- [ ] Second-opinion review: tenancy model against BCB's Sistema de Informações de Crédito tenancy precedent.

**Exit:** Two named sandbox institutions are onboarded and visible end-to-end from the SBS-side UI. Both can self-service rotate credentials. Per-institution dashboards render real data.

**May 25 scope.** Reduced. Per-institution dashboard (already in prototype-v2 HTML) rendering data from the real API for at least one named institution. **Deferred to post-sprint (June/July):** self-service credential portal, full per-institution operations surface (rate limit configuration, scope management, credential rotation), Tier B onboarding flows. See [ADR 0025](adr/0025-may-25-sprint-critical-path.md).

### Part 9 — Production Readiness

Goal: this stack is deployable, operable, recoverable, and audit-able by a vendor inheriting it from SBS, on bare-metal or in Azure.

- [ ] Helm chart finalised, with values for dev / staging / SBS / Azure overlay. Tested by a `helm install` on a fresh k3d cluster, no manual steps.
- [ ] Terraform modules for **bare-metal** (network, storage, secrets, Postgres, Redis, vLLM node) **and** Azure tenancy (AKS, Azure Database for PostgreSQL, Key Vault, ACR).
- [ ] Runbooks for every operational scenario: ingestion stalled, validator failing, vLLM out of memory, Postgres replication lag, certificate rotation, credential leak, taxonomy version cutover.
- [ ] DR plan: RPO / RTO targets (illustrative), backup procedure, restore drill script, evidence of a successful restore on a fresh cluster.
- [ ] Load testing with **k6**: signed Tier 1 path at target throughput, batch ingestion under load, agent pipeline back-pressure.
- [ ] Security audit: gitleaks, trivy (image scan), bandit (SAST), CycloneDX SBOM, SLSA provenance attached to releases.
- [ ] SBS handoff package: architecture diagram (one page), data flow diagram, threat model, ADR set printed, runbook bundle, demo recording, on-prem deployment guide, vendor extension guide.
- [ ] Demo run-throughs ×3 against the production-shape stack (not the dev compose).
- [ ] Plain-language operations summary readable by Veronica.
- [ ] Second-opinion review: handoff package against the World Bank SupTech reference architecture.

**Exit:** A vendor can clone the repo, deploy to a fresh cluster, run the conformance suite, restore from backup, and respond to a runbook scenario — all without contacting SBS.

**May 25 scope.** Deferred entirely. The demonstration runs on a Mac with Homebrew services. A brief k6 load test on Day 9 gives one illustrative number for "how does it scale." **This is a deliberate, time-bounded exception to [CLAUDE.md](../CLAUDE.md) north-star principle #1 (one-command deploy); the exception ends when Part 9 lands (June/July 2026).** **Deferred to post-sprint (June/July):** full deployment substrate (Docker Compose for dev, Helm chart, Terraform modules), production hardening, capacity planning, deployment to SBS Azure tenancy or bare-metal. See [ADR 0025](adr/0025-may-25-sprint-critical-path.md).

### Part 10 — AI/ML Evaluation Framework

Goal: every classifier, ranker, embedding, and agent decision has a documented evaluation method, a baseline number, a regression test, and a path to re-evaluation when models change.

- [ ] Evaluation dataset: labelled sample of complaints with taxonomy categories, severity, resolution status. Versioned. Stored separately from training data.
- [ ] Per-model evaluation harness: BETO classifier, XGBoost ranker, embeddings (retrieval quality), agent decisions (precedent-vs-current case agreement).
- [ ] Metrics defined per model: F1 / precision / recall for classification; NDCG / MAP for ranking; recall@k for retrieval; agreement-with-human-reviewer for agents.
- [ ] Baseline numbers committed — each labelled measured / illustrative / target.
- [ ] Regression test gate: a PR that drops any metric by more than a configurable threshold fails CI.
- [ ] Drift monitoring: data drift, prediction drift, label drift — Grafana dashboards.
- [ ] Re-evaluation runbook: how to refresh the eval set, how to re-baseline, who approves.
- [ ] ADR for the eval framework.
- [ ] Plain-language explainability note: how each model is evaluated, in language Mariela can read.
- [ ] Second-opinion review: framework against CGAP's "Responsible AI in SupTech" guidance.

**Exit:** Every model in the stack has a numeric baseline (with label), a regression test, and a Grafana drift dashboard. A PR that regresses any model fails CI.

**May 25 scope.** Deferred entirely. The demonstration uses curated synthetic data. **Deferred to post-sprint (July):** per-model evaluation datasets, metrics, regression gates, drift dashboards, evaluation against real complaint data once data access is in place. See [ADR 0025](adr/0025-may-25-sprint-critical-path.md).

### Part 11 — Standards Pack & Reporting Taxonomy Distribution

Goal: SBS publishes a machine-readable Anexo 1-A that any institution, vendor, or other regulator can consume — turning the taxonomy from a PDF into a versioned, testable, distributable artifact.

- [ ] JSON Schema for every Anexo 1-A object, generated from the YAML taxonomy, validated against the OpenAPI spec.
- [ ] Code lists published as canonical CSV + JSON, with stable identifiers and a deprecation policy.
- [ ] Validation rules library: cross-field rules expressed declaratively, runnable against a payload, with stable rule IDs that errors reference.
- [ ] OpenAPI 3.1 spec with full examples, error catalogue, RFC 9457 problem types, security schemes documented.
- [ ] Batch manifest schema for Tier 2 ingestion.
- [ ] Error catalogue: every stable error code with description, RFC 9457 type URI, severity, and remediation guidance.
- [ ] Sample payloads for every taxonomy variant, including edge cases (Unicode, deprecated codes, partial submissions).
- [ ] Versioning policy: SemVer for the Standards Pack, breaking-change procedure, deprecation timelines.
- [ ] Distribution: publish the Standards Pack as an OCI artifact and as a tagged GitHub release with a SHA-256 manifest.
- [ ] Plain-language Standards Pack overview readable by Sergio and Veronica.
- [ ] ADR for the versioning and distribution policy.
- [ ] Second-opinion review: Standards Pack against EBA reporting taxonomy distribution and HMRC's Making Tax Digital schemas.

**Exit:** A third party (vendor, supervised institution, peer regulator) can download v1.0.0 of the Standards Pack, validate sample payloads, generate clients, and integrate — entirely from the published artifact, with no access to SBS staff.

**May 25 scope.** Reduced. Standards pack v0.1 (OpenAPI + JSON Schema) generated and version-stamped as part of Part 7's May 25 work. **Deferred to post-sprint (June/July):** SemVer versioning policy, code lists distribution, OCI artifact publishing, GitHub release distribution, full standards pack governance. See [ADR 0025](adr/0025-may-25-sprint-critical-path.md).

## Daily discipline

- Morning: open part's chat, paste git log + status, get task list
- Small commits, run scripts/demo.sh after meaningful changes (from Part 4)
- Stuck >30 min: Template 4 second opinion
- Non-trivial decision: line in DECISIONS.md before moving on
- Architectural decision: ADR before implementation
- End of day: update PLAN.md, push, 3-line status in DECISIONS.md
- End of part: complete second opinions, summary in PLAN.md, new chat for next part
