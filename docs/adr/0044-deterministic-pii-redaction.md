# ADR 0044 — Deterministic PII redaction for the P11A demo ingestion path

- **Status:** Accepted
- **Date:** 2026-05-24
- **Target prompt / Part:** P11A (live ingestion / redaction / data-quality slice)
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

The supervisor UI's LiveIngestionPanel needs to demonstrate a credible end-to-end Tier 1 submission, including PII redaction. The institutional ingest path (`POST /v1/complaints`) already excludes the Anexo 1-A PII-bearing fields by ADR 0026, so the production-shaped surface never sees DNI, full names, or free-text phone/email patterns in the structured payload. The narrative field (`DET_REC`) is the residual risk: a real institution can — and in production almost certainly will — embed PII in the narrative even though the schema does not require it.

P11A introduces a sandbox-only ingestion endpoint that accepts a realistic Anexo-1A-shaped payload **with** PII fields, so the regulator audience can see redaction work in real time. The design needs to keep three commitments simultaneously:

1. Raw PII goes through the redactor on the way to canonical storage and never reaches `complaints`, `agent_runs`, `audit_events`, SSE payloads, the supervisor-UI response, or any LLM / cloud surface.
2. The redaction must be **deterministic** — the same input always produces the same redacted text and the same set of detected entities. The sandbox makes no cloud calls and ships no statistical model.
3. The audit chain must be able to re-run the redaction against the raw narrative if a future policy version changes; the policy version is therefore a first-class field.

## Decision

### D1 — Regex-and-allowlist engine, no LLM, no NER model, no cloud call

`api/sbs_api/redaction/engine.py` is a single-file pure function. Five entity kinds are detected:

| Kind          | Detection                                                                 |
| ------------- | ------------------------------------------------------------------------- |
| `pii_id`      | 8-digit Peruvian DNI, optional `DNI` prefix.                               |
| `pii_phone`   | Peruvian mobile (`+51 9XX XXX XXX`, `9XX XXX XXX`, `9XXXXXXXX`).           |
| `pii_email`   | Simple RFC-shaped email.                                                  |
| `pii_account` | 12–19 digit account/card number with optional spaces or hyphens.          |
| `pii_name`    | Exact match against `DEMO_KNOWN_NAMES` allowlist (accented + ASCII forms).|

Soles amount patterns (`S/ 700`, `S/.700`, `700 soles`, `monto 700`) are explicitly excluded from the account regex so an amount is never redacted as PII. The kinds map 1:1 to the `pii_*` literals in the existing `anonymizer_call.output.redactions[].kind` enum in `docs/schemas/agent_run.schema.json`, so the redaction record validates against the JSON Schema without any change.

### D2 — Stable, numbered replacements per kind

Detection order is left-to-right after overlap resolution. Replacements follow `<KIND_N>` where `N` increments per kind:

```
<PERSON_1>, <PERSON_2>, …
<DNI_1>, …
<PHONE_1>, …
<EMAIL_1>, …
<ACCOUNT_1>, …
```

A supervisor reading the redacted narrative can therefore co-reference entities (same person mentioned twice → same `<PERSON_1>` both times). The replacements are tested for stability in `tests/test_redaction_engine.py`.

### D3 — `policy_version = "pii-redaction-demo-v1"`

The version string is attached to every redaction record (in the engine output, in the `anonymizer` tool_call's `input.policy_version` and `output.policy_version`, and as a column on the `raw_complaints` row). Future policy revisions bump the version; the raw narrative kept in `raw_complaints` lets a re-run compare the two passes.

### D4 — `raw_complaints` is the only PII-bearing store

A new table, `raw_complaints`, holds the original payload + raw narrative. The Alembic migration is `20260524_0001_raw_complaints`. Three guarantees:

- Canonical `complaints.description_text` carries only the redacted narrative.
- No code path outside `sbs_api.demo_ingestion` and explicit operator queries reads `raw_complaints`. The `cockpit`, `findings`, `audit`, and `approvals` builders do not import `RawComplaint`. The invariant is asserted by `tests/integration/test_no_raw_pii_egress.py`.
- The row carries `storage_policy = "restricted-demo-pii-v1"` and the `redaction_policy_version` applied at ingest.

### D5 — Browser-visible BEFORE preview is masked

The HTTP response envelope returns `redaction_diff.before_masked` (a server-side **partial mask** of the raw narrative — `<PERSON:masked>`, `****1234`, `***123`, `c***@com`, `****9999`) and `redaction_diff.after_redacted` (the fully redacted text). The full raw narrative never leaves the FastAPI process. `entities[]` in the response carry `kind`, `rule_id`, `span`, `replacement`, `confidence` — but never `matched_value`.

### D6 — Demo endpoint, not production institutional surface

The redaction pipeline is wired into `POST /v1/internal/demo/simulate-submission` (shared-secret + supervisor session), **not** into `POST /v1/complaints`. The production-shaped Tier 1 path remains as it was (mTLS + OAuth + HMAC, no PII fields in the schema). The demo endpoint exists so the LiveIngestionPanel can drive a real backend; production deployments that need redaction at the institutional surface will adopt this engine in a follow-up Part.

## Precedent

- [market-comparators.md](../research/market-comparators.md) — CFPB Consumer Complaint Database, FCA Smarter Communications, EBA reporting practices. All three publish public complaint datasets where free-text narratives are pre-processed for PII before disclosure. The pattern this ADR adopts — deterministic, versioned, audit-trail-friendly redaction with raw kept in restricted storage — is the same shape CFPB describes in its "scrubbing" documentation.
- **NIST SP 800-188 (de-identification of personal information)** — the policy-versioning + reversibility-by-restricted-raw pattern.
- **Yelp `detect-secrets`** — already cited in `docs/research/supply-chain-precedents.md`. Same operating principle (regex-and-allowlist deterministic detection with stable kind labels) applied to a different PII class.

## Divergence

- **No statistical NER / no LLM.** Real Spanish-language regulatory deployments typically combine regex with a per-institution NER model (CFPB does this internally) or a managed service. The sandbox refuses cloud / LLM calls (see CLAUDE.md governance), so the name detector is a fixed allowlist. Production will replace `DEMO_KNOWN_NAMES` with either an institution-provided allowlist or a Spanish-language NER service; the engine interface does not change.
- **No address detector.** The `anonymizer_call` schema enum reserves `pii_address`; the engine currently does not detect addresses. Adding one is a non-breaking change.
- **Tool name reuse.** The new agent_run rows use `tool_name = "anonymizer"` so the existing `findings/builder.py:_extract_anonymizer` selector keeps working unchanged. The agent_name is the new `live-ingestion-orchestrator`.

## Consequences

**Locks in.**

- Five entity kinds (`pii_name`, `pii_id`, `pii_account`, `pii_phone`, `pii_email`) mapped to the existing JSON Schema enum.
- `policy_version = "pii-redaction-demo-v1"` as the first labelled version. Future revisions bump this.
- `<KIND_N>` replacement format.
- Raw PII storage exclusive to `raw_complaints`; canonical / SSE / audit / agent / UI surfaces redacted only.
- Browser-visible BEFORE is a server-side mask, never the raw narrative.

**Leaves open.**

- Address detection.
- Per-institution allowlists / NER integration.
- Whether the engine is hoisted into the institutional `POST /v1/complaints` path in a future Part.

**Trail.** Implementation landed on branch `part-11a-live-ingestion-redaction-dq` alongside ADR 0045 (data-quality), the `raw_complaints` migration, the demo endpoint, and the LiveIngestionPanel rewiring.
