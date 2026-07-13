# ADR 0001 — Three-layer agent architecture (agents / tools / supervisors)

- **Status:** Accepted
- **Date:** 2026-05-21 (drafted), 2026-05-27 (finalised for Part 12)
- **Target prompt / Part:** Part 12 (Agent Layer)
- **Supersedes:** The original Proposed entry at the same number
  ("MCP + A2A + LangGraph three-layer agent architecture"). The
  three-layer intent (agents / tools / supervisors) is retained; the
  concrete MCP / A2A / LangGraph stack is rejected in favour of an
  in-house tool-calling loop (see Rejected alternatives). The slug is
  kept verbatim so the ADR-index anchor for "0001" still resolves.
- **Superseded by:** —
- **Deciders:** Maintainer, with input from the May 26 SBS workshop
  (Diego, Supervisor, the Supervisor).

## Context

By Part 11 the prototype ingests complaints, redacts PII, normalises
taxonomy, runs the 27-field Annex 1-A data-quality checks, and
records one `live-ingestion-orchestrator` agent_run per submission.
The Findings page renders four panels with placeholder data: BERT
classification, Feature importance (XGBoost), Agent reasoning, and
Draft summary all show "—" or seeded values. The May 27 demo needs
those panels backed by real agent execution.

Two pressures shape the design:

1. **Regulator-grade auditability** — every reasoning step must be
   reconstructable from the database without re-running the model.
   That has been the contract from Prompt 10 onward
   (`docs/schemas/agent_run.schema.json`).
2. **PII isolation** — no raw PII reaches any agent. The redaction
   layer is the bright line; agents only see canonical text.

The May 26 SBS workshop transcript names the two demo headliners
explicitly: a Triage agent that "finds the 20% that matter" (Diego's
phrase) and an Investigation agent that builds the evidence bundle
the analyst will edit. Two more agents — Synthesis (executive
brief) and a pair of scaffolded roadmap agents (Taxonomy
Harmonizer, Cross-Source Correlator) — round out the architecture
without claiming live capability we do not have.

## Decision

We adopt a **three-layer architecture** for the agent stack:

- **Layer 1 — Agents (orchestrate).** Five named agents:
  `triage`, `investigation`, `synthesis`, `taxonomy-harmonizer`,
  `cross-source-correlator`. Three are real (call tools, decide
  routing, produce structured `final_output`); two are scaffolded
  (`ReplayProvider`-driven, ship the architecture without the
  capability claim). Each agent declares an `allowed_tools` list
  enforced by the runtime — the agent cannot exceed its capability
  surface even if a model emits a forbidden tool name.
- **Layer 2 — Tools (execute).** Ten registered tools in
  `api/sbs_api/agents/tools/`. Each tool has a JSON-Schema parameter
  block, a deterministic version string, and an async `run(ctx, **kwargs)`
  method. Every tool invocation is captured in
  `agent_runs.tool_calls` per the locked Prompt 10 contract.
- **Layer 3 — Supervisors (approve).** The existing `approvals`
  package already enforces this: no agent output reaches an
  institution without a human decision (`approval-decided` audit
  row).

The agent runtime is a **tool-calling loop** (not LangGraph). The
loop alternates between `provider.complete()` and tool execution
until the provider returns a final text or `max_iterations=5` is
hit. This keeps the dependency surface tiny — `httpx` + the
in-house tool registry — and makes the trace identical to what
production OpenAI/Azure deployments emit.

The runtime depends on a `ModelProvider` protocol. Four
implementations exist:

| Provider | Purpose | When used |
|---|---|---|
| `OnPremProvider` | OpenAI-compatible HTTP client against a self-hosted vLLM endpoint. Falls back to MockProvider when unreachable. | Default in dev/staging when `SBS_API_VLLM_BASE_URL` resolves. |
| `ReplayProvider` | Reads pre-recorded turn sequences from `fixtures/replay/<agent>/<complaint>.json`. | Demo determinism, scaffolded agents, CI. |
| `MockProvider` | Deterministic stub keyed by `agent_name`. | Unit tests, the on-prem fallback. |
| `CloudProvider` | Permanently-gated scaffold. Even when `SBS_API_CLOUD_LEGAL_APPROVED=true`, `complete()` raises `NotImplementedError`. | Not used. Document of intent. |

## Precedent

- **CFPB Consumer Complaint Database** — published taxonomy + open
  data API + narrative-governance pattern (consent + de-identification
  before publication). The split between data-collection layer and
  analytics layer that we encode as "tools execute, agents
  orchestrate" is the same separation CFPB uses operationally.
  Source: [market-comparators.md §2.1 — US CFPB Consumer Complaint
  Database](../research/market-comparators.md#21-us-cfpb-consumer-complaint-database).
- **UK FCA complaints reporting regime** — PS25/19 reform separates
  the firm-submitted return (data layer) from the FCA's supervisory
  analytics over that return (decision layer). Human supervisors
  retain the publication and enforcement decision; the analytics
  surface ranks and benchmarks but does not act. This matches our
  "supervisors approve" layer.
  Source: [market-comparators.md §2.3 — UK FCA complaints reporting
  regime](../research/market-comparators.md#23-uk-fca-complaints-reporting-regime).
- **BIS Project Ellipse** — strong reference for integrated
  structured/unstructured data and early-warning indicators with
  prudential metrics held under human review. The Ellipse pattern
  ships analytics that *propose* and humans that *decide*; our
  Triage → Investigation → human-approval chain encodes that
  precedent.
  Source: [market-comparators.md §6 — BIS Project
  Ellipse](../research/market-comparators.md#6-comparator-table-summary)
  row, alongside BIS FSI Insights 73 (AI data governance, third-party
  dependency, supervisory expectations).

The three-layer split (agent / tool / supervisor) is the
agent-design analogue of OWASP-ASVS Level 2 isolation: capability
declared up front, surface bounded, decisions recorded.

## Divergence

Two deliberate departures from the comparators:

1. **No live cloud LLM call.** The May 27 demo runs against
   ReplayProvider (demo invariants) and OnPremProvider (with a mock
   fallback). The CloudProvider scaffold exists but raises. SBS has
   not signed off on cross-border data residency for prompt content
   that derives from supervisory-grade narratives — even though we
   redact PII before the agent sees it, the joined feature shape
   carries supervisory judgment which is itself sensitive.
2. **Five agents, three real.** Comparators ([BIS Project Aurora](../research/market-comparators.md#6-comparator-table-summary)
   in particular) describe larger, multi-component analytics systems
   that span synthetic data, privacy-enhancing technologies, and
   cross-institution signals. The prototype ships only the two
   agents the May 26 workshop named as demo-critical (Triage,
   Investigation) plus the executive brief path (Synthesis). The
   other two (Taxonomy Harmonizer, Cross-Source Correlator) ship as
   **scaffolded** — a visible architectural slot for the v0.2 work
   item, not a capability claim.

## Consequences

- The `tool_name` enum in `docs/schemas/agent_run.schema.json` grew
  from five entries to fifteen. Additive only; no existing row
  shape is invalidated.
- `agent_runs.status` gained `in_progress` as an additive sixth
  value (migration `20260527_0001_agents_status`). The four
  terminal states are unchanged.
- The Findings detail endpoint surfaces three new top-level keys
  (`executive_summary`, `anomaly`, `similar_complaints`) populated
  from the new agents' `final_output`. The legacy `classifier` and
  `narrative-drafter` selectors remain as fallbacks so older
  seeded data still renders.
- The cockpit snapshot grew an `agent_stats` block (three new
  tiles). The block is optional so older clients still parse the
  snapshot.

## Rejected alternatives

- **LangGraph or LlamaIndex Agents.** Heavy dependency for one
  five-iteration tool-calling loop. Re-evaluated for v0.2 when
  cross-agent state needs to persist across complaints.
- **One mega-agent.** A single agent that holds every tool is
  conceptually simpler but loses the per-agent capability
  declaration that maps cleanly to regulator review.
- **Async worker dispatch (arq).** The synchronous in-session
  invocation keeps the demo path simple and avoids a Postgres
  visibility race (the cockpit reads agent_runs almost immediately
  after the SSE `complaint.received` event). v0.2 work item: move
  to arq when latency budget permits.

## Demo path (locked invariants)

For `BCO-2026-000001` the chain must produce, deterministically:

- Triage classification = `undisclosed-fees-credit` (0.87)
- Investigation top feature = `narrative_mentions_fee_undisclosed`
  (+0.27)
- Investigation anomaly = 0.74 / threshold 0.70 / `anomaly_flag=true`
- Investigation draft narrative OMITS "comisión por mantenimiento"
  (Analyst's scripted edit lands on the gap)
- Synthesis executive summary is non-empty plain Spanish
  (Superintendent / the Supervisor variants both populated)

These invariants are encoded in the ReplayProvider fixture under
`api/sbs_api/agents/fixtures/replay/` and asserted by
`tests/integration/test_agent_pipeline.py`.
