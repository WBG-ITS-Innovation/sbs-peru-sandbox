# Architectural Decision Records

This index lists every ADR with its current status. New ADRs are scaffolded via `/adr-new <slug>`.

Statuses: `Proposed` (queued, not yet written), `Draft` (file exists, content in progress), `Accepted` (locked — referenced by code or docs), `Superseded` (replaced by a later ADR, retained for history).

Every Accepted ADR must contain a `## Precedent` section citing a specific section of a research file under [docs/research/](../research/) — typically [market-comparators.md](../research/market-comparators.md) for regulator-domain decisions or [supply-chain-precedents.md](../research/supply-chain-precedents.md) for operational supply-chain decisions. The `benchmark-checker` subagent enforces this; the rule is *specificity of section and comparator*, not filename.

## Index

| #    | Slug                                  | Status   | Target prompt / Part | One-line description |
| ---- | ------------------------------------- | -------- | -------------------- | -------------------- |
| 0001 | three-layer-mcp-a2a-langgraph         | Proposed | Prompt 9 / Part 1    | MCP + A2A + LangGraph three-layer agent architecture |
| 0002 | taxonomy-as-configuration             | Proposed | Part 2               | Anexo 1-A taxonomy as YAML, loaded into Pydantic models, single source of truth |
| 0003 | api-authentication                    | Proposed | Part 3               | mTLS + OAuth 2.0 client_credentials + HMAC request signing |
| 0004 | error-model-rfc-9457                  | Proposed | Part 3               | RFC 9457 problem+json with stable error codes and type URIs |
| 0005 | synthetic-data-strategy               | Proposed | Part 4               | Synthetic complaint generator: 10k complaints, 3 scenarios, deterministic seeds |
| 0006 | ml-serving-and-mcp-exposure           | Proposed | Part 5               | BETO + XGBoost + pgvector served via MCP tool servers; MLflow registry |
| 0007 | a2a-inter-agent-protocol              | Proposed | Part 6               | A2A as the inter-agent communication contract; Agent Cards for discovery |
| 0008 | case-file-design                      | Proposed | Part 6               | Case file as the accumulating artifact across specialist agents |
| 0009 | human-in-the-loop-state-machine       | Proposed | Part 6               | Approval queue states: proposed → reviewed → approved/rejected → executed → notified |
| 0010 | sdk-distribution-and-versioning       | Proposed | Part 7               | SDK generation for .NET / Java / Python / TypeScript; SemVer; deprecation policy |
| 0011 | tenancy-and-credential-model          | Proposed | Part 8               | Per-institution tenancy, credential rotation, scope and rate-limit policy |
| 0012 | ai-ml-evaluation-framework            | Proposed | Part 10              | Per-model eval datasets, metrics, regression gates, drift dashboards |
| 0013 | standards-pack-distribution           | Proposed | Part 11              | Standards Pack versioning, OCI artifact + GitHub release distribution |
| 0014 | dev-llm-stack                         | Proposed | Prompt 6             | Dev-time LLM stack and tooling — flagged for cross-model review with Antoine |
| 0015 | cross-review-llm-backend-azure        | Proposed | Prompt 1.5 / Part 2  | Cross-review LLM backend: Azure OpenAI via WBG tenancy (no personal openai.com keys); aligns with likely SBS Azure-tenancy production posture |
| 0016 | secret-scanner-stack                  | Accepted | Prompt 2 / Part 1    | gitleaks + detect-secrets locally; gitleaks only in CI; committed baseline is a developer aid, not a CI gate |
| 0017 | dependency-update-tooling-dependabot  | Accepted | Prompt 2 / Part 1    | Dependabot (not Renovate) for Part 1, weekly schedule, grouped minor+patch for pip and npm; docker ecosystem deferred to Part 9 |
| 0018 | sbom-format-cyclonedx-via-syft        | Accepted | Prompt 2 / Part 1    | SBOM format is CycloneDX JSON produced by syft; implementation workflow deferred to Part 9 |
| 0019 | dependency-review-threshold-high      | Accepted | Prompt 2 / Part 1    | dependency-review-action fails on `high` and above; `moderate` reported but non-blocking; revisit at Part 9 |
| 0020 | env-handling-policy                   | Accepted | Prompt 2 / Part 1    | `.env` and `.env.*` never committed; secrets via GitHub Actions secrets in CI and local `.env` for developers; no personal data in repo |
| 0021 | package-manager-uv                    | Accepted | Prompt 3 / Part 1    | uv (Astral) is the Python package manager and project tool; root `pyproject.toml` + committed `uv.lock`; harness `requirements-harness.txt` retired |
| 0022 | python-version-3-12                   | Accepted | Prompt 3 / Part 1    | Python 3.12 only; `requires-python = ">=3.12,<3.13"`; no CI matrix on Python versions |
| 0023 | workspace-layout-uv-members           | Accepted | Prompt 3 / Part 1    | uv workspace with members `api/`, `agents/`, `tools/`, `sdk/`; `frontend/` and `infra/` outside the workspace; flat per-member layout for now |
| 0025 | may-25-sprint-critical-path           | Proposed | Prompt 4 / Part 1    | May 25 sprint kickoff scope: Parts 2/3/4 full, Parts 5/6/7/8/11 reduced, Parts 9/10 deferred entirely; PLAN.md restructure. Proposed until a sprint-phasing comparator lands in docs/research/. |

## How to add an ADR

1. Run `/adr-new <slug>`.
2. The file is created at `docs/adr/NNNN-<slug>.md` and a row is added here as `Proposed`.
3. Fill in the Precedent and Divergence sections. Run `/benchmark-check docs/adr/NNNN-<slug>.md`.
4. When the ADR is referenced by code or docs, change status to `Accepted` here.
5. If superseded later, change status to `Superseded` and add a pointer to the new ADR.

## How to amend an ADR

ADRs are append-only in spirit. To change a locked decision, open a new ADR that supersedes the old one, and update both files' statuses. Do not silently edit an Accepted ADR.
