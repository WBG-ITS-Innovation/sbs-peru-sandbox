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

## The 10 parts

### Part 1 — Foundation
- [ ] Repo + uv project initialized
- [ ] Tooling: ruff, pyright strict, pre-commit, gitleaks, conventional commits, spectral
- [ ] Project structure: api/, agents/, tools/, frontend/, infra/, docs/, scripts/, sdk/
- [ ] Docker Compose: Postgres+pgvector, Redis, vLLM (Qwen 2.5 14B), Prometheus, Grafana, Loki, OTel collector
- [ ] OTel collector configured, Grafana provisioned
- [ ] CI: lint + test + type-check on PR
- [ ] ADR 0001 written: MCP+A2A+LangGraph three-layer

**Exit:** `docker compose up` clean, CI green

### Part 2 — Data Model & API Skeleton
- [ ] config/taxonomies/sbs-peru-v1.yaml — full Annex 1-A
- [ ] Pydantic v2 models from YAML loader
- [ ] Alembic baseline migration (all tables defined)
- [ ] FastAPI with /health, /health/ready, /health/live
- [ ] Scalar docs site at /docs
- [ ] structlog + OTel tracing on every endpoint
- [ ] GET /v1/complaints returns empty list with proper headers
- [ ] ADR 0002: Taxonomy as configuration
- [ ] Second opinion: Template 6 (OpenAPI review) — GPT-5

**Exit:** Scalar docs render, trace visible in Grafana

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

## Daily discipline

- Morning: open part's chat, paste git log + status, get task list
- Small commits, run scripts/demo.sh after meaningful changes (from Part 4)
- Stuck >30 min: Template 4 second opinion
- Non-trivial decision: line in DECISIONS.md before moving on
- Architectural decision: ADR before implementation
- End of day: update PLAN.md, push, 3-line status in DECISIONS.md
- End of part: complete second opinions, summary in PLAN.md, new chat for next part