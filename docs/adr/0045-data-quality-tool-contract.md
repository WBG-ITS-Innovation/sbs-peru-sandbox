# ADR 0045 — Deterministic data-quality tool contract for the P11A demo ingestion path

- **Status:** Accepted
- **Date:** 2026-05-24
- **Target prompt / Part:** P11A (live ingestion / redaction / data-quality slice)
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

The P11A demo ingestion path needs to demonstrate that the prototype catches missing or implausible Anexo 1-A-like fields before a complaint reaches the cockpit, and that those checks are deterministic, auditable, and not produced by an LLM. The supervisor audience needs to see specific, rule-id-tagged issues — "narrative mentions a digital wallet but channel_operation is blank" — and a recommended action they can apply, not a probabilistic "consider reviewing."

Two related constraints shape the design:

1. **No LLM, no cloud call.** CLAUDE.md governance is explicit, and the redaction story in ADR 0044 commits to a fully on-prem deterministic pipeline. The DQ checker has to live in the same regime.
2. **No widening of the `agent_run` JSON Schema's closed `tool_name` enum.** The existing enum is `bert_classifier | xgboost_ranker | regex_taxonomy | anonymizer | qlik_lookup`. Adding a `data_quality_check` tool_name would require touching the schema doc and would propagate through every consumer that validates against it.

## Decision

### D1 — Pure regex + code-list module under `api/sbs_api/data_quality/`

The checker is one module: `api/sbs_api/data_quality/checks.py:run_checks`. It is a pure function over (a) the structured Anexo-1A-like fields the demo endpoint received and (b) the **redacted** narrative produced by `sbs_api.redaction`. No I/O, no random, no LLM, no third-party service. The function is tested for input-output stability in `tests/test_data_quality_checks.py`.

### D2 — Three buckets: `errors`, `warnings`, `suggested_enrichments`

The DQ report uses a stable shape:

```python
{
  "errors": [{"rule_id", "field", "message"}, ...],
  "warnings": [{"rule_id", "field", "message"}, ...],
  "suggested_enrichments": [{"rule_id", "field", "suggested_value", "evidence"}, ...],
  "extracted_fields": {"amount_claimed_extracted": "700", ...},
  "policy_version": "dq-demo-v1",
}
```

`errors` are structural failures (missing required field). `warnings` are non-blocking concerns (missing optional field, unknown code-list value, narrative too short). `suggested_enrichments` carry a candidate value the supervisor could apply — extracted amount, suggested channel — with a free-form `evidence` string that quotes the redacted narrative span responsible.

### D3 — Stable rule IDs

Each row carries a kebab-case `rule_id`. The full set enumerated in the module docstring + ADR:

- `missing-institution-complaint-id`
- `missing-narrative`
- `missing-product`
- `missing-motive`
- `unknown-product-code`
- `unknown-motive-code`
- `missing-channel-operation`
- `unknown-channel-operation-code`
- `wallet-clue-without-mobile-channel`
- `amount-mentioned-without-claim` (sub-IDs: `amount-pen-symbol-dot`, `amount-pen-prefix`, `amount-soles-suffix`, `amount-monto-keyword`)
- `narrative-too-short`

Rule IDs are stable across runs so an audit dashboard can pin a filter on a specific rule. Adding a rule is a non-breaking change; renaming or removing one is a breaking change and requires an ADR amendment.

### D4 — `policy_version = "dq-demo-v1"`

The version string is attached to every report. Future rule revisions bump the version. Tests assert the constant is present in every emitted report.

### D5 — DQ output lives in `agent_runs.final_output`, not as a new tool_call

The existing JSON Schema at `docs/schemas/agent_run.schema.json` closes the `tool_name` enum at five literals. To avoid widening the schema (per the P11A stop conditions), the DQ report is written into the agent_run's `final_output` under the key `data_quality`:

```python
final_output = {
  "complaint_id": "...",
  "raw_complaint_id": "...",
  "redaction": { "policy_version": "...", "entity_count_by_kind": {...} },
  "data_quality": { ... DQ report ... },
  "summary": "first 120 chars of redacted narrative",
}
```

The agent_run's `tool_calls` therefore contains one entry — the `anonymizer` call covering the redaction step (which is in the enum). The findings builder's `tool_name == "anonymizer"` selector keeps working unchanged. Consumers that need the DQ report read it from `final_output.data_quality`. Tests cover the round-trip.

### D6 — Status mapping: `success` on clean, `partial` on blocking errors

If `errors == []`, the agent_run status is `success`. If any `errors` row is present, the status is `partial` with a `run_error` of:

```python
{"code": "DATA_QUALITY_ERRORS", "message": "<N> data-quality error(s) recorded; see final_output.data_quality.errors"}
```

The complaint is still persisted (DQ does not block persistence) — the partial status signals to the supervisor that the canonical row was written but with structural issues for the institution to repair.

### D7 — Sandbox-scoped code-list allowlists

The known-product / known-motive / known-channel-operation allowlists in `api/sbs_api/data_quality/checks.py` cover the codes the cockpit / findings views already exercise. They are explicitly documented as **sandbox-scoped** and are **not** the canonical Anexo 1-A code list. Replacing them with the full ADR 0026 / Part 11 standards-pack code lists is a non-breaking change.

## Precedent

- [market-comparators.md](../research/market-comparators.md) — CFPB Consumer Complaint Database publishes per-row validation issues alongside complaints; FCA Smarter Communications applies declarative validation rules with stable IDs on inbound submissions; the World Bank Group's data-quality tooling for regulator-supervised reporting (referenced in the supply-chain precedents file) uses the same three-bucket pattern (errors / warnings / suggestions).
- **W3C Data Catalog Vocabulary (DCAT) — data quality dimensions** — completeness + plausibility + consistency map to the buckets here.
- **OpenAPI 3.1 problem+json (RFC 9457)** — already adopted across the API surface for error envelopes (ADR 0028). The DQ report shape echoes that pattern (stable identifier + message + field) so a supervisor reading both feels the same.

## Divergence

- **No model-based enrichment.** Production complaint pipelines often run a small classifier to extract amount / channel / product from free text. The sandbox uses pure regex for the same purpose (amount extraction, wallet keyword detection). Production may swap the regex out for a model; the response shape stays the same.
- **DQ in `final_output`, not `tool_calls`.** The natural shape would be a new `data_quality_check` tool_name in the JSON Schema enum. The schema-widening stop condition from the P11A brief is honoured by lifting DQ to `final_output`. The trade-off is that downstream consumers that expect every tool execution to be a `tool_call` will need to look in `final_output` for this one — documented here and in the agent_run schema notes.
- **Sandbox code lists.** The allowlists are illustrative, not canonical Anexo 1-A. Production replaces them with the standards-pack code-list distribution (Part 11).

## Consequences

**Locks in.**

- Three-bucket report shape: `errors` / `warnings` / `suggested_enrichments`.
- Stable rule IDs; renaming is a breaking change.
- `policy_version = "dq-demo-v1"` as the first labelled version.
- `agent_runs.final_output.data_quality` as the persistence location.
- Status mapping `success` ↔ no errors, `partial` ↔ ≥ 1 error.

**Leaves open.**

- Whether DQ is hoisted to a `tool_call` entry in a future schema revision (would require widening the JSON Schema enum + a coordinated ADR amendment).
- Adding model-based extractors for amount / channel / product.
- Replacing the sandbox code lists with the Part 11 standards-pack distribution.

**Trail.** Implementation landed on branch `part-11a-live-ingestion-redaction-dq` alongside ADR 0044 (redaction). The full agent_run row produced by the demo endpoint is asserted against the existing JSON Schema in `tests/integration/test_live_ingestion_endpoint.py`.
