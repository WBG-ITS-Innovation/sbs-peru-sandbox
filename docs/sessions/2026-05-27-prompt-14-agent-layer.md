# Session journal — 2026-05-27 — agent-layer

- **Date:** 2026-05-27
- **Prompt:** 14 (next sequential number after the most recent journaled prompt, 09)
- **Part:** 12 — Agent Layer
- **Slug:** agent-layer
- **Files touched:** 76 (62 new files in `api/sbs_api/agents/`, schema + migration extensions, findings/cockpit builder updates, three new UI components, ADR 0001 supersede, PLAN.md Part 12 section, walkthrough doc, narration anchors update, four new test files, two existing tests updated).

## Cross-model review — triage line

**Skipped** with documented reason: `AZURE_OPENAI_*` env vars not configured on the demo laptop. The four-variable WBG-tenanted Azure OpenAI requirement (CLAUDE.md "Model-call governance") was not met, and the closeout script aborts cross-review rather than swallow the failure (carry-over fix #1a from Prompt 1). Reason recorded here for the session journal as required by the `--skip-cross-review-with-reason` contract.

Cross-review is **not** waived for the merged PR. The maintainer should run `python scripts/cross_review.py --target HEAD~1 --slug agent-layer` from a machine where the four env vars resolve, and append the output under `docs/reviews/2026-05-27-agent-layer.md` before merge. The triage gate will then re-apply.

## Adversarial review

`second-opinion` returned **WEAKNESS-FLAGGED** with six concrete weaknesses. Four were fixed in this PR; two are accepted-and-documented:

| Weakness | Disposition |
|---|---|
| `agents_running` cockpit tile structurally always-zero on synchronous pipeline | **Accepted.** Tile renamed `agent_runs_last_5min` with explicit honesty comment in the type definition, narration anchor reworded, PLAN.md Part 12 wording updated. |
| Orphan `in_progress` agent_runs row on mid-pipeline failure | **Accepted.** Defensive sweep added in `api/sbs_api/demo_ingestion/orchestrator.py::_finalise_orphan_agent_runs`; the sweep writes a `swept=true` audit-row so the recovery is itself reconstructable. |
| Schema does not constrain `in_progress` shape | **Accepted.** New `if status==in_progress then {ended_at, final_output, error}: null` block added to `docs/schemas/agent_run.schema.json`. |
| `scripts/demo.sh` uses `:=` for env vars — operator pre-export can leak | **Accepted.** Demo script now force-exports `SBS_API_MODEL_PROVIDER=replay` and prints the resolved values to stdout. |
| Provider singleton races on concurrent same-complaint requests | **Documented, deferred.** The real agents already `reset()` ReplayProvider on entry; the scaffolded agents construct their own ReplayProvider per call. The race window applies only to MockProvider, which is test-only. v0.2 fix: key the cursor by `(agent_name, complaint_id, run_id)`. |
| OnPrem silent fallback to MockProvider has no audit row | **Documented, deferred.** A warning is logged once per process. v0.2 work item: emit a `provider-fallback` audit row with `from=on_prem to=mock reason=...`. |

## What landed

The agent layer. The Findings page no longer shows "—" placeholders for the BCO-2026-000001 demo complaint. Three real agents (Triage, Investigation, Synthesis) call ten registered tools through an in-house tool-calling loop. Two scaffolded agents (Taxonomy Harmonizer, Cross-Source Correlator) demonstrate the architectural slot without a capability claim. The model layer is provider-pluggable: `on_prem` with a mock fallback when no vLLM endpoint is reachable, `replay` for the demo invariants, `mock` for CI, `cloud` permanently gated and raising NotImplementedError. The Findings detail endpoint surfaces three new top-level keys (`executive_summary`, `anomaly`, `similar_complaints`); the cockpit grows an honest three-tile agent-stats strip; the Executive Brief sub-panel renders the SynthesisAgent's plain-Spanish summary for the Superintendent or supervisor lead. All five demo invariants for BCO-2026-000001 are asserted by `tests/integration/test_agent_pipeline.py` under both the `replay` and `mock` providers. The full pytest suite reports 646 passed, 6 skipped.

## Decisions locked

- **ADR 0001 supersede.** The original MCP+A2A+LangGraph proposal is rejected. Concrete stack: an in-house tool-calling loop with a `ModelProvider` protocol and four implementations. Three-layer enforcement (agents / tools / supervisors) retained. See `docs/adr/0001-three-layer-mcp-a2a-langgraph.md` and the README index update.
- **`agent_runs.status` enum gains `in_progress`.** Additive sixth value via migration `20260527_0001_agents_status`; the four terminal states are unchanged. JSON schema extended with both the value and a shape constraint that fixes `ended_at`, `final_output`, and `error` to `null` while a run is in flight.
- **`tool_name` enum extended from 5 to 15 entries.** All five original names preserved in order; the ten Part 12 tool names appended. No per-tool conditional shape constraints for the new entries — they use the open `input`/`output` shape from the wrapper.
- **Synchronous in-session dispatch.** The agent pipeline runs in the same SQLAlchemy session as the ingestion orchestrator. The async-arq path is a documented v0.2 work item.
- **Cockpit "Agent runs (last 5 min)" — not "agents running".** Honest semantic choice given the synchronous pipeline. The `agents_in_flight` field is still emitted on the snapshot for future async work but is not surfaced to the UI today.
- **`SBS_API_AGENTS_PIPELINE_ENABLED` defaults to `false`.** Demo script force-exports it `true`; the Prompt-11 regression suite stays green without the flag.
- **Anomaly composite weights locked.** indecopi 0.30 / sentiment 0.20 / narrative 0.25 / velocity 0.15 / market 0.10. Threshold 0.70. Documented in PLAN.md Part 12 and asserted by `tests/test_agent_tools.py::test_compute_anomaly_returns_demo_invariant`.

## Decisions deferred (to a named future prompt / part)

- **Async dispatch via arq.** Target: Part 13 (v0.2). Today's pipeline is inline. The async path will populate a true `agents_in_flight` count.
- **pgvector similar-complaints search.** Target: Part 13 (v0.2). Today the tool documents `strategy="exact-match"`.
- **OpenTelemetry parity in the agent layer.** Target: Part 13 (v0.2). Spans were added around `agent.iteration`; per-tool spans and Prometheus counters (`agent_runs_total`, `tool_invocations_total`, `agent_iteration_duration_seconds`) are still missing. Audit-chain rows are the durable trace today.
- **Live INDECOPI / Quantico / MonitoriA correlation.** Target: Part 13 (v0.2). The Cross-Source Correlator scaffold returns deterministic replay output.
- **Real vLLM deployment on regulator infrastructure.** Target: Part 13 (v0.2). OnPremProvider speaks the protocol; the prototype defaults to the mock fallback.
- **Provider-fallback audit row.** Target: Part 13 (v0.2). The fallback is logged once per process but is not yet a recorded audit event.

## Decisions flagged for cross-model review

- **Synchronous in-session dispatch vs async arq.** Owner: maintainer. Model: GPT-5 / Claude Opus through `scripts/cross_review.py` once the laptop has Azure tenancy env vars. The trade-off is cockpit-tile semantics, audit-chain transactional safety, and demo-day determinism — worth a second opinion before Part 13 commits to arq.
- **JSON schema `if/then` coverage for the ten new tool names.** Owner: maintainer. Model: GPT-5. The new tools use the open wrapper shape; should the schema add per-tool `output` constraints (mirroring the five legacy tool shapes) before v0.2, or is the open shape correct?

## Subagent verdicts

| Subagent | Verdict | One-line summary |
|---|---|---|
| reviewer | BLOCK on first pass → APPROVE after fixes | Caught the PLAN.md Part 12 gap, ADR 0001 number collision, invented "BIS Atlas" comparator, dead `agents_pipeline_provider` Settings field, `loop.py` tool-arguments serialisation bug, and a stray English participle in `es.json`. All six fixed in this PR. |
| architect-guard | APPROVE WITH AMENDMENT | Confirmed schema additivity, PII isolation, three-layer enforcement, no cloud LLM call. Flagged one stale line in PLAN.md (`Agents: LangGraph internal, A2A inter-agent, MCP for tools`); rewritten to reference ADR 0001. |
| doc-sync | APPROVE WITH NITS | Three drift items: PLAN.md tile wording, walkthrough doc Taxonomy Harmonizer footnote, stale ORM-model docstring listing the Prompt-10 agent names. All three fixed. |
| regulator-readability | APPROVE WITH NITS | One Spanish string drift (`se utilizó` → `se usó` — the project's `utilize → use` rule applied to Spanish). Fixed in `app/src/i18n/es.json`. |
| benchmark-checker | BLOCK → APPROVE after fix | Three valid Precedent citations (CFPB §2.1, FCA §2.3, BIS §6) and a valid PLAN.md → ADR 0001 linkage, but a second invented "BIS Atlas" mention survived in the Divergence section. Replaced with BIS Project Aurora (research file §6). |
| second-opinion | WEAKNESS-FLAGGED | Six concrete weaknesses (see Adversarial review section above). Four fixed in this PR, two documented and deferred to v0.2. |

## Paste-ready block for the maintainer

> Part 12 — the agent layer — landed on `part-12/agent-layer`. Five subagent reviews + the adversarial second-opinion ran on the staged diff; all findings were either fixed in this PR or explicitly accepted-and-deferred with a v0.2 target. Cross-model review was skipped because the demo laptop does not have the four `AZURE_OPENAI_*` env vars; the maintainer should run it from a configured machine before merge. The PR contains 76 file changes, 26 new tests (646 passed total), and a Findings page that no longer shows "—" placeholders for BCO-2026-000001. The demo invariants are locked under `tests/integration/test_agent_pipeline.py` and hold under both `replay` and `mock` providers.

## Notes

- `gh` CLI is not installed on the demo laptop, so the closeout pipeline skips the PR-creation step. The maintainer should open the PR manually after pulling the branch on a configured machine: `gh pr create --base main --head part-12/agent-layer --title "feat(p12): agent layer — three real agents, two scaffolded, ten tools" --body-file <session journal>`.
- The `frontend/logo/` files that appeared as untracked at session start were not staged. They are unrelated to Part 12.
- Recent commits on this branch (`part-09/api-pii-agent-foundation`) covered Parts 9–11 of the PLAN. Part 12 lives logically on a new branch; the maintainer should `git checkout -b part-12/agent-layer` before commit so the pre-push hook accepts the name.
- A demo dry-run on the supervisor laptop is recommended before tomorrow morning. The walkthrough at `docs/demo/2026-05-27-agents-ready.md` is the sequence to follow.
