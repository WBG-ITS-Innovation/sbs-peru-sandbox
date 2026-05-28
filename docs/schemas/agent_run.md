# `agent_run` schema contract

- **Status:** Accepted (v1).
- **Owner:** Prompt 10 (supervisor UI wiring) and Prompt 12 (agent layer).
- **Purpose:** Defines the durable execution-trace record written by every agent that processes a complaint. The supervisor UI reads from this table to render the "agent reasoning" panel on the Findings drilldown and the "evidence chain" panel on Approvals.
- **Why this exists as a contract, not a convention:** Prompt 10 seeds rows that the UI consumes; Prompt 12 replaces those rows with live agent output. Without a written contract the two prompts will drift, the UI will break at P12 integration, and the May 25 demo will display a polished surface over incoherent data. This document is the integration gate. As long as `tests/integration/test_agent_run_schema.py` is green, the UI does not break when P12 lands.
- **JSON Schema artifact:** [`agent_run.schema.json`](agent_run.schema.json) is the machine-readable form. The narrative below explains intent; the JSON Schema is the executable check.

## Precedent and divergence

**Precedent.** [Market comparators §5.E "On-prem / sovereign agentic layer"](../research/market-comparators.md#5e-on-prem--sovereign-agentic-layer) identifies LangGraph as the orchestration substrate, citing its support for "long-running stateful agents, durable execution, streaming, persistence, and human-in-the-loop workflows." `agent_run` is the durable-execution surface of that substrate: a per-run row with a per-tool-call sub-record, sufficient to reconstruct every agent decision after the fact. Tool-call shapes for the XGBoost ranker draw on [§5.D "Predictive risk scoring and explainability"](../research/market-comparators.md#5d-predictive-risk-scoring-and-explainability), which scopes XGBoost + SHAP as decision support with named feature contributions, not automated enforcement.

**Divergence.** LangGraph's native checkpoint format is opaque-by-default; we materialise the trace into a relational table with explicit columns so that:

- Supervisors and auditors can query the trace with SQL, not framework-specific tooling.
- The supervisor UI reads the same rows whether the agent layer is LangGraph, AutoGen, Semantic Kernel, or a hand-written orchestrator. The contract survives the orchestrator choice.
- Partial failures are first-class (see [`status`](#status-state-machine)), so the UI does not need to infer failure from missing fields.

## P11A note — `live-ingestion-orchestrator` and data-quality placement

The P11A demo ingestion path (`POST /v1/internal/demo/simulate-submission`) writes agent_runs rows with `agent_name = "live-ingestion-orchestrator"` and `agent_version = "live-ingestion-orchestrator-0.1.0"`. The kebab-case name and the `<name>-<semver>` version both validate against the existing pattern constraints.

The deterministic data-quality report from `sbs_api.data_quality` is **not** persisted as a new `tool_call`. The `tool_name` enum in [`agent_run.schema.json`](agent_run.schema.json) is closed at `bert_classifier | xgboost_ranker | regex_taxonomy | anonymizer | qlik_lookup`, and ADR 0045 commits to not widening it in P11A. Instead, the DQ report sits in `final_output.data_quality` with the documented shape:

```json
{
  "final_output": {
    "complaint_id": "BCO-2026-1234567",
    "raw_complaint_id": "<uuid>",
    "redaction": { "policy_version": "pii-redaction-demo-v1", "entity_count_by_kind": {"pii_id": 1, "pii_name": 1} },
    "data_quality": {
      "errors": [], "warnings": [], "suggested_enrichments": [],
      "extracted_fields": {}, "policy_version": "dq-demo-v1"
    },
    "summary": "first 120 chars of redacted narrative"
  }
}
```

The `tool_calls` array carries one entry — the `anonymizer` call (already in the enum) covering the redaction step. The findings builder's `tool_name == "anonymizer"` selector therefore keeps working unchanged.

Status mapping for live-ingestion-orchestrator runs:

- `success` — DQ produced zero errors. `error` is null. `final_output` is the dict above.
- `partial` — DQ produced ≥ 1 error. `error = {"code": "DATA_QUALITY_ERRORS", "message": "..."}`. `final_output` still carries the DQ report so a supervisor can act on the errors.

The full schema check is exercised against a live agent_run row by `tests/integration/test_live_ingestion_endpoint.py:test_demo_endpoint_writes_pii_free_agent_run`.

## Table: `agent_runs`

The JSON Schema is named `agent_run` (singular — it describes the shape of one record); the Postgres table is `agent_runs` (plural — matches the repo convention `institutions`, `complaints`, `batches`).


| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | `uuid` | no | Primary key. Server-assigned UUID stored as `String(36)`. Stable across retries; a retry starts a new row. |
| `complaint_id` | `text` | no | Foreign key to `complaints.complaint_id`. Matches the repo-wide complaint-id pattern `^[A-Z0-9]{1,4}-\d{4}-\d{6,10}$` (e.g., `BCP-2026-001234`). One complaint may have many runs (triage, classification, narrative drafting). |
| `agent_name` | `text` | no | Stable identifier, kebab-case. Examples: `triage`, `classifier`, `narrative-drafter`, `cross-source-correlator`, `query-author`. |
| `agent_version` | `text` | no | Format: `<agent_name>-<semver>`. Example: `triage-0.3.1`. The prefix repeats `agent_name` deliberately so that an `agent_version` string is self-describing in audit exports. |
| `started_at` | `timestamptz` | no | ISO 8601 with explicit timezone. Stored as UTC; rendered in the UI in `America/Lima`. |
| `ended_at` | `timestamptz` | yes | Null only while the run is in flight. A run that ends in `timeout` still sets `ended_at` (to the time the timeout fired). |
| `status` | `text` | no | One of `success`, `partial`, `failed`, `timeout`. See [state machine](#status-state-machine). |
| `tool_calls` | `jsonb` | no | Ordered array of tool-call records. May be empty (a degenerate run that failed before any tool). See [`tool_calls` shape](#tool_calls-element-shape). |
| `final_output` | `jsonb` | yes | The agent's final structured output, shape per `agent_name`. Null when the run did not produce a final output (`failed` before completion, or `partial` with no usable output). |
| `error` | `jsonb` | yes | Structured error record when `status in ('partial', 'failed', 'timeout')`. Null otherwise. Shape: `{code: string, message: string, tool_name?: string}` where `tool_name` names the tool that triggered the run-level failure (a per-tool error also lands inside `tool_calls`). |

### Status state machine

Exactly one of:

- `success` — all tool calls succeeded; `final_output` is non-null; `error` is null.
- `partial` — at least one tool call failed but the agent produced a usable `final_output` anyway (e.g., classifier returned a low-confidence label after BERT timed out and the regex fallback fired). `error` is non-null and names the degradation.
- `failed` — the agent could not produce a usable output. `final_output` is null; `error` is non-null.
- `timeout` — the run exceeded its time budget. `ended_at` is set to the timeout instant; `final_output` may be null or partial; `error.code = "AGENT_TIMEOUT"`.

The UI renders `partial` and `timeout` distinctly from `failed`. A `partial` finding can still be sent to Approvals; a `failed` run is surfaced as an operator-visible incident in the Audit screen.

## `tool_calls` element shape

Each element of `tool_calls` is an object:

| Field | Type | Nullable | Description |
| --- | --- | --- | --- |
| `tool_name` | `string` | no | One of: `bert_classifier`, `xgboost_ranker`, `regex_taxonomy`, `anonymizer`, `qlik_lookup`. New tool names require an amendment to this document. |
| `tool_version` | `string` | no | Format: `<tool_name>-<semver>` (e.g., `bert_classifier-1.4.0`) for in-house tools, or an upstream version string passed through verbatim for external services (e.g., `qlik_lookup-saas-2025.11`). |
| `started_at` | `string` | no | ISO 8601 with explicit timezone. |
| `ended_at` | `string` | no | ISO 8601 with explicit timezone. Always set, even on `failed` or `timeout` — the failure instant is itself audit-relevant. |
| `input` | `object` | no | Shape depends on `tool_name`; see [per-tool schemas](#per-tool-input--output-schemas). |
| `output` | `object` | yes | Shape depends on `tool_name`. Null when the tool failed before producing any output. |
| `status` | `string` | no | One of `success`, `failed`, `timeout`. (No `partial` at tool level — a tool either returned a usable output or it did not.) |
| `error` | `object` | yes | Structured `{code, message}` when `status != "success"`. Null on success. |

`tool_calls` is ordered by `started_at`. The UI may render a Gantt-style timeline; the order is load-bearing.

## Per-tool input / output schemas

These shapes are part of this contract. Adding a field is non-breaking; removing or renaming one is breaking and requires an ADR amendment.

### `bert_classifier`

Spanish complaint-narrative classifier. BETO / RoBERTa-BNE via ONNX (see [Locked architectural decisions](../PLAN.md#locked-architectural-decisions)).

- **`input`**: `{text: string, locale: "es-PE", max_tokens: integer}`. `text` is the anonymized narrative (post-`anonymizer`).
- **`output`**: `{label: string, confidence: number (0..1, two-decimal precision in the UI), top_k: [{label: string, confidence: number}], model_version: string}`. `label` is an Annex 1-A category code. `top_k` carries the top three classes for the UI's "top 3 probabilities" panel.

### `xgboost_ranker`

Severity / priority ranker with SHAP-style feature attribution.

- **`input`**: `{complaint_id: uuid, features: object}` where `features` is the materialised feature vector used at inference time (named keys, numeric values).
- **`output`**: `{score: number (0..1), rank_band: "low"|"medium"|"high"|"critical", feature_contributions: [{feature_name: string, contribution: number, direction: "positive"|"negative"}], model_version: string}`. `feature_contributions` carries the top eight features for the Findings drilldown's feature-importance panel. Per §5.D this is decision support, not a complete legal explanation.

### `regex_taxonomy`

Pattern matching against the Annex 1-A taxonomy regex bundle. Used both as a classifier fallback when BERT is unavailable and as a sub-pattern detector that runs alongside BERT.

- **`input`**: `{text: string, taxonomy_version: string}`.
- **`output`**: `{matches: [{pattern_id: string, label: string, span: [integer, integer], matched_text: string}], taxonomy_version: string}`. `span` is a UTF-8 character offset pair into `text`. The UI uses the spans to highlight evidence in the narrative panel.

### `anonymizer`

PII redaction. Always runs before any tool that consumes narrative text.

- **`input`**: `{text: string, policy_version: string}`.
- **`output`**: `{anonymized_text: string, redactions: [{kind: "pii_name"|"pii_id"|"pii_account"|"pii_phone"|"pii_email"|"pii_address", span: [integer, integer]}], policy_version: string}`. The UI renders `redactions` as visibly-redacted spans in the original-narrative view.

### `qlik_lookup`

Cross-source lookup against the existing SBS Qlik analytical layer. Returns institution-level context (recent complaint volume, prior findings, segment baseline).

- **`input`**: `{institution_id: string, lookup_keys: [string]}`. `lookup_keys` names the analytical objects requested (e.g., `["complaint_volume_28d", "prior_findings_180d", "segment_baseline"]`).
- **`output`**: `{results: object, source_version: string, fetched_at: string}`. `results` is keyed by `lookup_keys`; values are passed through from Qlik with no reshaping. `fetched_at` is ISO 8601.

## Partial-failure invariants (seeded examples)

The supervisor UI must handle three named partial-failure shapes on Day 1, before any live agent writes a row. The WS0 seed script writes at least one of each:

1. **BERT timeout.** `tool_calls` contains a `bert_classifier` entry with `status="timeout"` and `error.code="BERT_TIMEOUT"`, followed by a `regex_taxonomy` entry with `status="success"`. The run's `status` is `partial`; `final_output` carries the regex-fallback classification with a confidence reduction flag.
2. **XGBoost unavailable.** `tool_calls` contains an `xgboost_ranker` entry with `status="failed"` and `error.code="XGBOOST_UNAVAILABLE"`. The run's `status` is `partial`; `final_output` is present (the classification stands) but carries no `rank_band`.
3. **Anonymizer error.** `tool_calls` contains an `anonymizer` entry with `status="failed"` and `error.code="ANONYMIZER_INTERNAL_ERROR"`. The run's `status` is `failed` (no downstream tool may consume un-anonymized narrative); `final_output` is null. This case must surface in the Audit screen as an operator-visible incident.

The seed script lives under `scripts/seed_demo_narrative.py` (Prompt 10 WS0). The schema-validation test lives at `tests/integration/test_agent_run_schema.py` and runs against seeded rows now and against live Prompt 12 output later.

## Timestamps and locale

- Storage: `timestamptz` in Postgres, normalised to UTC at write time.
- Wire format: ISO 8601 with explicit timezone designator (`Z` or `±HH:MM`). Bare local datetimes are invalid.
- UI rendering: `America/Lima` (UTC−05:00, no DST). Locale `es-PE` is the default; `en-US` is offered via the toggle.

## `final_output` shape by agent name

`final_output` is the one field the JSON Schema deliberately leaves open (`type: object` with no further constraint), because each agent name carries a different payload. The shapes below are the contract — P10 seed writers and P12 live writers must produce them; the supervisor UI's Approvals screen reads from them. New keys are additive (coordinated PR); renaming or removing a key is breaking.

| `agent_name` | Required keys | Notes |
| --- | --- | --- |
| `triage` | `route_to`, `priority`, `system_signal`, `system_signal_reasons` | `route_to` ∈ {`info-only`, `review`, `reject`} — informational only; `priority` ∈ {`low`, `medium`, `high`}; `system_signal` is the boolean the orchestrator uses to gate Investigation; `system_signal_reasons` is an array of enum codes (`OUTAGE_KEYWORD`, `FRAUD_KEYWORD`, `AMOUNT_THRESHOLD`, `REGULATORY_BREACH_INDICATOR`) — never raw narrative excerpts. |
| `classifier` | `classification`, `confidence`, `sub_patterns` | `classification` is an Annex 1-A code; `confidence` ∈ [0, 1]; `sub_patterns` is an array of `{label, evidence_span}` for patterns not in Annex 1-A but surfaced (e.g., `comisión por mantenimiento`). `confidence_degraded: true` is added when partial-run regex fallback supplied the label. |
| `narrative-drafter` | `draft_text`, `language`, `evidence_refs` | `draft_text` is the analyst-editable summary shown on Findings; `language` is `es-PE` or `en-US`; `evidence_refs` is an array of `{tool_name, tool_call_index}` pointing back into `tool_calls` so the UI can highlight cited evidence. |
| `cross-source-correlator` | `composite_score`, `threshold`, `channel_contributions`, `anomaly_flag` | `composite_score` and `threshold` ∈ [0, 1]; `channel_contributions` is an array of `{channel, value, contribution}` where `channel` ∈ {`complaints`, `social`, `indecopi`, `plavia`, `internal`}; `anomaly_flag` triggers the cockpit anomaly card. |
| `query-author` | `query_text`, `recipient_institution_id`, `due_at`, `severity` | `query_text` is the drafted supervisory query; `recipient_institution_id` references `institutions.institution_id`; `due_at` is ISO 8601 with timezone; `severity` ∈ {`low`, `medium`, `high`, `critical`}. |

Adding a sixth agent requires adding a row here, updating any seed or live writer in the same PR, and noting the change in [Revision history](#revision-history).

## Backwards compatibility

Every object in the JSON Schema sets `additionalProperties: false`. Every change — additive or not — is therefore a coordinated schema PR: writers and readers move in lockstep, not silently. Additive changes (new optional fields, new tool names, new agent rows) bump the **minor** version of the schema's `$id`. Breaking changes (removing a column, changing a field's type, narrowing an enum, dropping a required key from a `final_output` shape) bump the **major** version and require an ADR amendment. The seed script and any live writers are updated in the same PR; the integration test catches drift between writer and reader. Coordinated, not silent.

## Revision history

- 2026-05-22 — v1 introduced as the Prompt 10 ↔ Prompt 12 integration gate.
- 2026-05-27 — `triage.final_output` carries `system_signal` (boolean) and `system_signal_reasons` (array of enum codes). Investigation is gated on `system_signal == true`; the per-complaint Investigation invocation path is removed. Additive change — keys are new and optional for older runs.
