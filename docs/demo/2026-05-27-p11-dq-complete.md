# P11 DQ completion — 2026-05-27

Closes the Annex 1-A data-quality gap left open by the P11 sandbox
work. The previous closeout (`docs/demo/2026-05-26-p11-sandbox-close.md`)
shipped six DQ rules — required-field presence on four high-value
fields plus two narrative heuristics — and explicitly deferred the
remaining 21. This document records what landed in the deferred
work, the canonical code lists committed alongside, and the
rule-by-rule audit footprint.

The browser-walk evidence still owed against `p11-sandbox-close`
(gates 5 + 6) is **unchanged by this work** and remains the next
piece of evidence required before tagging that prior closeout.

## Cadence + scope framing

This work extends the **annual Annex 1-A granular** path. SUCAVE
Formato 0224 monthly aggregate is untouched and remains the
regulator-cadence path. The 27-field validator runs at every
ingestion via the existing orchestrator, on both
`POST /v1/internal/demo/simulate-submission` (LiveIngestionPanel)
and `POST /v1/sandbox/complaints/granular` (institution CLI).
Scope remains conduct supervision only.

## 27-rule table

Six existing rules (DQ-A1A-001 .. DQ-A1A-006, kebab-case ids per
the original P11A engine) are unchanged and continue to surface in
the aggregated `data-quality-completed` audit event. The 21 new
rules (DQ-A1A-007 .. DQ-A1A-027) emit one `dq-rule-violated` audit
row each with the structured meta the prompt's audit contract
requires (`rule_id`, `field_path`, `observed_value`, `expected`,
`severity`).

| Rule | Field | Severity | Test coverage |
|---|---|---|---|
| DQ-A1A-001 (legacy: missing-institution-complaint-id) | institution_complaint_id (field 1) | error | `test_data_quality_checks.py` |
| DQ-A1A-002 (legacy: missing-narrative) | narrative (field 17) | error | `test_data_quality_checks.py` |
| DQ-A1A-003 (legacy: missing-product) | product (field 14) | error | `test_data_quality_checks.py` |
| DQ-A1A-004 (legacy: missing-motive) | motivo (field 15) | error | `test_data_quality_checks.py` |
| DQ-A1A-005 (legacy: unknown-product / unknown-motive code lists) | product / motivo | warning | `test_data_quality_checks.py` |
| DQ-A1A-006 (legacy: narrative-too-short / wallet-clue / amount-mentioned-without-claim) | narrative / amount_claimed | warning + info | `test_data_quality_checks.py` |
| DQ-A1A-007 | tipo_documento (field 2) | error | `test_007_happy`, `test_007_fail_when_missing` |
| DQ-A1A-008 | tipo_documento (code list) | warning | `test_008_happy`, `test_008_fail_on_unknown_tipo` |
| DQ-A1A-009 | numero_documento (field 3) | error | 4 tests (happy DNI, happy RUC, fail length DNI/RUC) |
| DQ-A1A-010 | codigo_cliente (field 5) | warning | `test_010_happy`, `test_010_warns_when_missing` |
| DQ-A1A-011 | fecha_ingreso (field 6) | error | `test_011_happy`, `test_011_fail_on_garbage` |
| DQ-A1A-012 | canal_ingreso (field 7) | error | `test_012_happy`, `test_012_fail_on_absence` |
| DQ-A1A-013 | canal_ingreso (Anexo A code list) | warning | `test_013_happy`, `test_013_warns_on_unknown_code` |
| DQ-A1A-014 | canal_respuesta (field 12, Anexo A code list) | warning | `test_014_happy`, `test_014_warns_on_unknown_code` |
| DQ-A1A-015 | ubigeo (field 13, INEI format) | warning | 3 tests (happy 6-digit, happy 4-digit, fail letters) |
| DQ-A1A-016 | submotivo (field 16) | warning | `test_016_happy`, `test_016_warns_when_missing` |
| DQ-A1A-017 | monto_reclamado (field 20, format) | warning | `test_017_happy`, `test_017_fail_on_string_amount` |
| DQ-A1A-018 | moneda (currency code list) | warning | `test_018_happy`, `test_018_warns_on_unknown_currency` |
| DQ-A1A-019 | estado (field 22) | error | `test_019_happy`, `test_019_fail_on_absence` |
| DQ-A1A-020 | estado (code list) | error | `test_020_happy`, `test_020_fail_on_invalid_estado` |
| DQ-A1A-021 | fecha_resolucion when estado=atendido | error | `test_021_happy_pendiente_no_resolucion`, `test_021_fail_atendido_without_fecha` |
| DQ-A1A-022 | resolucion_reclamo when estado=atendido (field 18) | error | `test_022_happy`, `test_022_fail_atendido_without_resolucion` |
| DQ-A1A-023 | fecha_resolucion < fecha_ingreso (temporal) | error | `test_023_happy`, `test_023_fail_inverted_dates` |
| DQ-A1A-024 | producto_bancaseguros when bancaseguros=si (field 25) | error | 3 tests (no trigger, fail no producto, happy with full triplet) |
| DQ-A1A-025 | motivo_bancaseguros when bancaseguros=si (field 26) | error | `test_025_happy`, `test_025_fail_trigger_without_motivo` |
| DQ-A1A-026 | submotivo_bancaseguros when bancaseguros=si (field 27) | warning | `test_026_happy`, `test_026_warns_trigger_without_submotivo` |
| DQ-A1A-027 | institution_id in onboarded-FI registry | warning | 3 tests (happy, fail unknown id, no-op when registry absent) |

Plus:

* `test_baseline_payload_fires_no_rules` — sanity: the canonical
  Annex-1A-complete payload triggers zero rules.
* `test_numero_documento_failure_does_not_expose_raw_value` — PII
  safety on `observed_value`.
* `test_all_severities_propagate_to_report` — error / warning
  rollup.

Total new unit tests: 51 (`tests/test_annex_1a_rules.py`).

## Code lists

All canonical code lists are committed as YAML under
`api/sbs_api/dq/codelists/`. Each carries a documentation header
naming the spec source and a `review_status` field.

| File | Spec source | Review status | Codes |
|---|---|---|---|
| `canales.yaml` | Anexo A — Res. SBS 04036-2022 (annexo.pdf, pp. 7–8) | `in_repo_spec` | 14 |
| `productos.yaml` | Anexo B — Res. SBS 04036-2022 (annexo.pdf, pp. 8–11) | `in_repo_spec` | 54 |
| `motivos.yaml` | Anexo C — Res. SBS 04036-2022 (annexo.pdf, pp. 12–16) | `in_repo_spec` | 58 |
| `submotivos.yaml` | Anexo D — Res. SBS 04036-2022 (annexo.pdf, pp. 17–18) | `in_repo_spec` | 82 |
| `tipo_documento.yaml` | field 2 (codes referenced but not enumerated in annexo.pdf) | **needs_review** | 6 |
| `estado_reclamo.yaml` | field 22 — enumerated verbatim in annexo.pdf p. 1 | `in_repo_spec` | 3 |
| `resolucion_reclamo.yaml` | field 18 — enumerated verbatim in annexo.pdf p. 1 | `in_repo_spec` | 3 |
| `moneda.yaml` | spec silent on field 20 currency — ISO 4217 sandbox set | **needs_review** | 6 |
| `bancaseguros_flag.yaml` | field 24 — enumerated verbatim in annexo.pdf p. 1 | `in_repo_spec` | 2 |
| `canal_reclamo.yaml` | Anexo A alias (fields 7 + 12) | `in_repo_spec` | 14 (via alias) |

Two lists (`tipo_documento`, `moneda`) carry `review_status:
needs_review` because the Reglamento references the codes but does
not enumerate them in `annexo.pdf`. Both files carry an explicit
"TBD — validate with Luis/Diego" header. The validator runs against
the sandbox set immediately so the demo path is functional; the
real-world set should be confirmed during institution onboarding
sign-off.

## Audit footprint per submission

Existing five-event chain (unchanged):

1. `demo-complaint-received`
2. `pii-redacted`
3. `canonical-complaint-persisted`
4. `data-quality-completed` — carries the **aggregated** counts for
   the legacy six rules. Unchanged shape and meta.
5. `complaint-triage-emitted`

New, additive:

6. `dq-rule-violated` — one row per Annex 1-A rule that fires. The
   `meta` carries: `rule_id`, `field_path`, `observed_value`,
   `expected`, `severity`, `policy_version` (`annex-1a-v1`), plus the
   existing `base_audit_meta` (agent_run_id, raw_complaint_id,
   redaction_policy_version, dq_policy_version, demo_scenario). PII-
   bearing fields surface as `"present"` / `"absent"` / `"invalid-format"`
   tokens in `observed_value`; non-PII codes are reported verbatim.

The `test_demo_endpoint_records_five_audit_events` assertion is
updated to use set-subset semantics so the new rows do not break
the existing invariant.

## Status mapping (institution receipt)

Unchanged contract — extended to roll in the new errors and warnings:

* `accepted` — no errors and no warnings from any rule (legacy or
  Annex 1-A).
* `accepted_with_warnings` — at least one warning (legacy or new);
  no errors.
* `rejected` — at least one error (legacy or new). Hard schema
  errors still return 4xx; DQ errors return 201 with `status:
  rejected` so the institution receives the receipt and the
  supervisor cockpit gets the audit chain.

## Status mapping (agent_run)

`agent_run.status` is now `partial` if **either** the legacy report
**or** the Annex 1-A report carries errors. `error` field carries
both counts:

```
"code": "DATA_QUALITY_ERRORS",
"message": "N legacy data-quality error(s) and M Annex 1-A error(s) recorded;
            see final_output.data_quality / annex_1a_data_quality."
```

## What was deferred

* The 6 legacy rules' kebab-case IDs are kept as-is for
  backwards-compatibility. A future cleanup could rename them to
  formal `DQ-A1A-001` .. `DQ-A1A-006` ids — additive doc work, not
  code.
* Code-list sign-off for `tipo_documento` and `moneda` — flagged as
  `needs_review` in the YAML headers.
* The browser-walk evidence owed against `p11-sandbox-close` is
  unchanged by this work and remains outstanding for that prior
  closeout. The new tag (`p11-dq-complete`) does not depend on it.

## Test command bundle

```bash
# Unit + integration coverage for the new rules + the amended audit
# assertion.
PYTHONPATH=$PWD/api .venv/bin/pytest \
    tests/test_annex_1a_rules.py \
    tests/integration/test_sandbox_granular_api.py \
    tests/integration/test_live_ingestion_endpoint.py \
    tests/integration/test_no_raw_pii_egress.py -q

# Full backend sweep (excluding env-broken suites that need `uv` on PATH):
PYTHONPATH=$PWD/api .venv/bin/pytest -q \
    --ignore=tests/test_demo_determinism.py \
    --ignore=tests/test_standards_pack_build.py \
    --ignore=tests/test_mtls_integration.py
# → 618 passed, 6 skipped

# Frontend:
( cd app && rm -rf .next && npm run typecheck && npm run build )
# → clean

# Demo path:
bash scripts/demo.sh --scale small
# → PASS in ~8s
```

## ADR pointers

* ADR 0044 — deterministic PII redaction (P11A).
* ADR 0045 — data-quality tool contract (P11A). The new
  `Annex1AReport` lives alongside the legacy `DataQualityReport`;
  the contract is additive.
* Res. SBS 04036-2022 — Reglamento de Gestión de Reclamos y
  Requerimientos (`annexo.pdf` in repo).
