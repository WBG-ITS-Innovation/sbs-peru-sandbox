# Agents-ready walkthrough — May 27, 2026

This is the Part 12 closeout walkthrough. Read in order; the
prerequisites (sandbox, DQ, redaction, taxonomy, UI polish) all
landed in Part 11.

## What changed

The Findings page no longer shows "—" placeholders for
BCO-2026-000001. Three agent runs (`triage`, `investigation`,
`synthesis`) populate the four panels and the new "Executive brief"
sub-panel. The cockpit gains a three-tile agent-stats strip.

The "Agents" architecture: three real agents (Triage,
Investigation, Synthesis) that call ten registered tools, plus two
scaffolded agents (Taxonomy Harmonizer, Cross-Source Correlator)
that use deterministic replay fixtures. The model layer is
provider-pluggable — on-prem vLLM by default with a mock fallback
when no endpoint is reachable.

## Sequence diagram

```
Institution                 SBS sandbox
    │
    │  POST /v1/internal/demo/simulate-submission
    ├─────────────────────────────────►│
    │                                  ├─ raw_complaints (PII)
    │                                  ├─ taxonomy_normalize()
    │                                  ├─ redact() — PII out
    │                                  ├─ complaints (canonical)
    │                                  ├─ run_dq_checks()
    │                                  ├─ run_annex_1a_checks()
    │                                  ├─ agent_runs: live-ingestion-orchestrator
    │                                  ├─ audit chain ×N (canonical-complaint-persisted, etc.)
    │                                  │
    │                                  │   ── if agents_pipeline_enabled ──
    │                                  ├─► TriageAgent
    │                                  │     ├─ query_dq_results
    │                                  │     ├─ query_taxonomy_normalizations
    │                                  │     └─ classify_complaint
    │                                  │   → final_output.classification, route_to
    │                                  │
    │                                  │   if route_to == 'investigation':
    │                                  ├─► InvestigationAgent
    │                                  │     ├─ rank_features
    │                                  │     ├─ compute_anomaly_score
    │                                  │     ├─ search_similar_complaints
    │                                  │     └─ draft_narrative
    │                                  │   → feature_attribution, anomaly, draft
    │                                  │
    │                                  ├─► SynthesisAgent
    │                                  │     ├─ query_audit_chain
    │                                  │     └─ summarize_for_executive
    │                                  │   → executive_summary (plain Spanish)
    │                                  │
    │                                  ├─► CrossSourceCorrelator (scaffold)
    │                                  │   → cross_source_signals (from replay fixture)
    │                                  │
    │                                  ├─ SSE: cockpit.complaint.received
    │                                  ▼
    │                              [supervisor UI]
    │
```

Per-stage, the orchestrator writes:

- `agent-run-started` audit row (status=in_progress)
- `agent-run-completed` audit row (with final status)
- one `agent_runs` row (terminal status, tool_calls trace,
  final_output)

## Running the demo

```bash
# Enable the agent pipeline + force the deterministic replay
# provider for the locked-invariant complaint.
SBS_API_AGENTS_PIPELINE_ENABLED=true \
SBS_API_MODEL_PROVIDER=replay \
bash scripts/demo.sh --scale small
```

The supervisor laptop browser walk:

1. Open `/cockpit`. The new Agent stats strip shows three tiles
   (Agent runs (last 5 min), Complaints triaged today, High-priority
   routes today). The synchronous pipeline (ADR 0001) means an
   "in-flight" count would always read 0; the 5-minute window is the
   honest demo-cadence proxy.
2. Click the anomaly card for BCO-2026-000001 to drill into
   `/findings/BCO-2026-000001`.
3. The four WS4 panels (Classification, Feature importance, Agent
   reasoning, Draft summary) all render real data.
4. Expand the Executive brief sub-panel under Draft summary. The
   superintendent-audience summary is in Spanish, listing the
   three coincident channels (INDECOPI, narrative, sentiment).
5. The draft summary deliberately omits "comisión por
   mantenimiento" — Lucía's scripted edit adds the missing phrase
   and saves the draft. The Audit screen then shows
   `narrative-saved` followed by the demo's
   `send-to-approvals` step.

## Locked demo invariants

| Invariant | Source | Test |
|---|---|---|
| Triage classification = undisclosed-fees-credit (0.87) | `fixtures/replay/triage/BCO-2026-000001.json` + `tools/classify.py` | `tests/test_agent_tools.py::test_classify_complaint_returns_demo_invariant` |
| Top feature = narrative_mentions_fee_undisclosed (+0.27) | `tools/rank_features.py` | `tests/test_agent_tools.py::test_rank_features_returns_demo_invariant_top_feature` |
| Anomaly = 0.74 / 0.70 / true | `tools/anomaly.py` | `tests/test_agent_tools.py::test_compute_anomaly_returns_demo_invariant` |
| Draft omits "comisión por mantenimiento" | `tools/narrative.py::DEMO_DRAFT` | `tests/test_agent_tools.py::test_draft_narrative_omits_comision_por_mantenimiento_for_demo` |
| Synthesis non-empty plain Spanish | `tools/narrative.py::DEMO_EXECUTIVE_SUMMARY_*` | `tests/integration/test_agent_pipeline.py::test_pipeline_demo_invariants_with_replay_provider` |

## Provider matrix

| `SBS_API_MODEL_PROVIDER` | Behaviour | Demo invariants hold? |
|---|---|---|
| `on_prem` (default) | vLLM client; falls back to MockProvider on connect failure. Logs warning once per process. | Mock fallback: yes (deterministic tools). Live vLLM: depends on the model. |
| `replay` | Reads `fixtures/replay/<agent>/<complaint>.json`. | Yes — fixtures are the invariants. |
| `mock` | Deterministic scripts keyed by agent_name. | Yes — tools are deterministic. |
| `cloud` | Raises `NotImplementedError`. Gated by `SBS_API_CLOUD_LEGAL_APPROVED=true`. | n/a |

## What was deferred

- **Async dispatch via arq.** Today's pipeline is synchronous in
  the same SQLAlchemy session as ingestion. This avoids a
  Postgres-visibility race with the cockpit SSE event. v0.2 work
  item.
- **pgvector similar-complaints search.** Falls back to exact-match
  on (product_category, motivo_code). v0.2 work item.
- **Live INDECOPI / Quantico social / MonitoriA audio
  correlation.** The Cross-Source Correlator agent ships scaffolded
  on the replay fixture. v0.2 work item.
- **Real vLLM deployment.** OnPremProvider talks to vLLM but the
  prototype runs the mock fallback by default. v0.2 work item.

## Audit trail

Each agent emits two audit events:

```
agent-run-started   actor=triage         object=complaint BCO-2026-000001
agent-run-completed actor=triage         object=complaint BCO-2026-000001  status=success
agent-run-started   actor=investigation  …
agent-run-completed actor=investigation  …
agent-run-started   actor=synthesis      …
agent-run-completed actor=synthesis      …
agent-run-started   actor=cross-source-correlator …
agent-run-completed actor=cross-source-correlator …
```

Note: the Taxonomy Harmonizer agent is wired but not invoked by
the orchestrator's demo path today. When a future call site
triggers it (manually from the cockpit or on a nightly schedule)
the agent emits `taxonomy-proposal-logged` audit rows (one per
proposed dictionary update) so the human reviewer has a complete
trace of every proposed change.
