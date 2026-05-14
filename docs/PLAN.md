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

### Part 7 — Specialist Agents I
- [ ] Pattern Detection Agent (temporal + cross-institution)
- [ ] Institutional Risk Agent (prudential lens — Mariela)
- [ ] Inter-agent handoffs via A2A
- [ ] Case file accumulation
- [ ] New MCP tools as needed
- [ ] ADR 0010: Multi-agent handoff pattern
- [ ] Second opinion: Template 1 (clustering thresholds) — Gemini 2.5 Pro

**Exit:** scenario replay produces case file with all three agents' contributions

### Part 8 — Specialist Agents II
- [ ] Conduct Agent (market-conduct lens — Mariela)
- [ ] Investigation Agent (evidence + drafting)
- [ ] Full Orchestrator flow: event → Triage → Pattern → (Institutional + Conduct parallel) → Investigation → approval queue
- [ ] ADR 0011: Specialist agent roles
- [ ] Second opinion: Template 1 (agent role boundaries) — GPT-5
- [ ] Second opinion: Template 5 (agent layer architecture) — Gemini 2.5 Pro

**Exit:** demo scenario produces fully-populated case file with draft alert in queue

### Part 9 — Frontend
- [ ] Next.js 14 + TS + Tailwind + shadcn/ui + TanStack Query + Recharts
- [ ] Auth against API
- [ ] Agent Workspace (hero): case file, reasoning trace, tool calls, evidence, draft editor, LangGraph viz
- [ ] Approval Queue UI
- [ ] Radar Dashboard (prudential)
- [ ] Alarm Dashboard (conduct)
- [ ] Ingestion Monitoring page
- [ ] i18n EN/ES
- [ ] ADR 0012: Frontend architecture
- [ ] Second opinion: Template 5 (UI credibility) — GPT-5 with vision

**Exit:** all pages render with real data, demo drivable through UI

### Part 10 — Polish, Deployment, Handoff, Demo
- [ ] Helm chart (tested on k3d)
- [ ] Terraform modules (network, storage, secrets)
- [ ] Vendor extension guide
- [ ] All ADRs finalized
- [ ] Runbook
- [ ] Kubernetes deployment guide
- [ ] README polished
- [ ] Python SDK polished + documented
- [ ] Grafana dashboards complete
- [ ] One-page architecture diagram
- [ ] Demo run-through ×3
- [ ] Loom backup recording
- [ ] scripts/demo.sh hardened
- [ ] Second opinion: Template 5 (final architecture) — Gemini 2.5 Pro
- [ ] Second opinion: Template 6 (final OpenAPI) — GPT-5
- [ ] Second opinion: Template 3 (final security) — GPT-5

**Exit:** clean demo three times in a row, all artifacts in place

## Daily discipline

- Morning: open part's chat, paste git log + status, get task list
- Small commits, run scripts/demo.sh after meaningful changes (from Part 4)
- Stuck >30 min: Template 4 second opinion
- Non-trivial decision: line in DECISIONS.md before moving on
- Architectural decision: ADR before implementation
- End of day: update PLAN.md, push, 3-line status in DECISIONS.md
- End of part: complete second opinions, summary in PLAN.md, new chat for next part