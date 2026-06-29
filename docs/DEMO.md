# Demo Script — Last DAy

**Length:** 6-8 minutes
**Audience:** WBG, SBS
**Setup:** local laptop, Docker Compose stack running, three browser tabs (Scalar API docs, Agent Workspace, Grafana)
**Backup:** Loom recording at the ready if anything breaks live

## Narrative arc

A coordinated mis-selling pattern emerges across three institutions over 10 simulated days. The system detects it, investigates it, drafts a regulatory response, and a human approves the action. Throughout, the architecture story is visible — protocols, on-prem inference, audit trails, vendor extensibility.

## Beat-by-beat

**Beat 1 — The integration story (60 seconds)**

Open Scalar API docs. Show OpenAPI spec for POST /v1/complaints. Highlight: Annex 1-A schema, RFC 9457 errors, idempotency, signed requests. Open the reference Python SDK, show how a bank would integrate in 20 lines.

> "Any supervised institution — bank, financiera, COOPAC — integrates against this spec. Tier 1 real-time for institutions with mature systems, Tier 2 batch for the rest. Same validation pipeline, same downstream processing. Proportional treatment by design."

**Beat 2 — A complaint arrives (45 seconds)**

Run `scripts/demo.sh post-complaint`. A signed mTLS request fires. Switch to Grafana, show the trace: request → validation → event emission → classification worker → embedding → pattern detection trigger. Real OpenTelemetry trace, real latencies.

> "Near-real-time. Every action audited. Every component observable. This is what the vendor inherits."

**Beat 3 — The pattern emerges (90 seconds)**

Run `scripts/demo.sh replay-scenario` — 200 synthetic complaints fire over 30 seconds, simulating 10 days of complaints across three institutions about an investment product. Switch to Agent Workspace. The Pattern Detection Agent has flagged a cluster.

Open the case file. Show: the cluster of related complaints, the temporal pattern, the cross-institution signal, the Investigation Agent's evidence gathering (similar past cases, relevant Anexo citations), the Drafting Agent's proposed alert.

> "Five specialist agents collaborated on this. Each runs its own LangGraph internally. They speak A2A to each other and MCP to the shared tool layer. The Investigation Agent pulled regulatory citations from Resolución 04036-2022 itself. None of this is hard-coded — these are agents reasoning over the data."

**Beat 4 — The Supervisor's two lenses (60 seconds)**

Switch to Radar dashboard — prudential view, institution-level risk scores trending. The three flagged institutions are climbing. Switch to Alarm — conduct view, incident-level spike on the investment product category.

> "The Supervisor's two supervisory lenses, same data, different vantage points. Prudential supervision sees institutional risk concentration. Market conduct sees the consumer harm pattern. Both views feed the same decision."

**Beat 5 — Human-in-the-loop (60 seconds)**

Back to Agent Workspace. Open the approval queue. The Drafting Agent's proposed action is pending: "Issue Article X notification to Banks A, B, C." Show the full audit trail: which agents touched it, which tools they called, what evidence supports it, the proposed draft text.

> "No agent takes regulatory action autonomously. Every action that affects a supervised institution sits in this queue until an SBS analyst approves it. Approval policy is SBS's call — the platform enforces whatever you decide."

Click approve. Webhook fires to the three institutions. Audit log records the human approver, timestamp, action.

**Beat 6 — The vendor handoff (45 seconds)**

Open VS Code. Show `/docs/adr/`, `/docs/extension-guide.md`, `helm/`, `terraform/`. Show the taxonomy YAML — point at the single file that defines Annex 1-A and explain that another region drops in a new YAML.

> "This is what we hand to the vendor. Architecture decision records, deployment artifacts, extension guide. Adding a new agent: one folder. New taxonomy: one YAML. New region: tenant_id and an i18n file. The platform is built to be inherited."

**Beat 7 — Close (30 seconds)**

> "Everything you saw runs on-prem. The Qwen model is in this laptop. No cloud dependency. No PII leaving the perimeter. Ready for a controlled pilot with one or two institutions when SBS chooses to authorize it."

## Things to have ready

- All three browser tabs pre-loaded
- `scripts/demo.sh` tested 3 times day 14 morning
- Loom backup recording
- One-pager handout: architecture diagram, deployment topology, vendor handoff checklist
- Repo URL ready to share

## What to NOT say

- "AI" without specifying which kind (classifier? agent? LLM?)
- "Real-time" (use "near-real-time")
- "Pilot bank" (use "supervised institution" or "participating institution")
- "Production" (use "deployable" or "reference implementation")
- Latency numbers as benchmarks (use "illustrative" or "target")
- Anything about Apache 2.0 or repository publication (subject to legal review)

## Reading the agent output (operator notes)

These notes explain two behaviors a first-time viewer often mistakes for a stall
or an error. Both are correct by design.

**The agent pipeline is selective, not exhaustive.** Triage runs inline on every
complaint as it is ingested. Investigation and synthesis do not. They run only on
the complaints triage flagged as high-signal — the pipeline routes a complaint
onward only when triage sets `route_to == 'investigation'`; otherwise it stops at
triage (see `api/sbs_api/agents/orchestrator.py`). As a result, most complaints
show "triaged, not escalated" in the workspace. That is the supervisory filter
working — separating the few cases that warrant investigation from the many that
do not — not the pipeline stalling. A demo run where most complaints stop at
triage is the expected, healthy state.

**`agent_runs.status = 'partial'` on the live-ingestion-orchestrator means a data-
quality rule fired, not that the run failed.** The ingestion orchestrator records
a run as `partial` when the data-quality validator (the legacy six-rule check or
the Annex 1-A rule set) returns one or more blocking errors for that complaint
(`api/sbs_api/demo_ingestion/orchestrator.py`, `run_status = "partial" if
has_blocking_errors else "success"`). `partial` is a non-failure terminal status:
the complaint was ingested and the DQ validator did its job by catching the issue.
It is distinct from `failed` and `timeout`, which do indicate the run did not
complete its work.
