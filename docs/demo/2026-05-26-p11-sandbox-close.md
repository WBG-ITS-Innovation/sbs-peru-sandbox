# P11 sandbox close — 2026-05-26

Day 2 of the Lima sprint. This document records what was merged from
`part-11/institution-real-connection` onto `part-09/api-pii-agent-foundation`,
what was verified, and where the remaining gaps are so the next prompt
can pick them up honestly.

## Cadence framing (refresher)

The work in this prompt closes the **annual Annex 1-A granular** gap.
It does not touch the **monthly Formato 0224 aggregate** path, which
remains untouched as the SUCAVE-backed regulatory cadence.

* Tier 1 NRT API — goal/target state for high-volume universal banks.
* Tier 2 batch — transitional bridge for institutions not yet
  API-ready. Same canonical Annex 1-A record on both paths.
* Cadence taxonomy: NRT API (high-volume, high-risk), daily
  (medium-volume), weekly/monthly batch (transition),
  quarterly/manual (low-volume).
* Scope is conduct supervision (Mariela's deputy department) only.
  Prudential is a separate deputy under the same SBS Twin Peaks
  framework and is not a user of this surface.

## What was merged

`git merge part-11/institution-real-connection` brought two commits
onto the active branch:

| Commit | Title | What it adds |
|---|---|---|
| `a0ca47c` | feat(p11a): wire live ingestion with redaction and data quality | `POST /v1/internal/demo/simulate-submission`, `raw_complaints` table + migration, deterministic regex redaction (`pii_name` / `pii_id` / `pii_phone` / `pii_email` / `pii_account`), deterministic DQ rules, agent_run write with redacted-only output, five audit-chain events, cockpit SSE delta. |
| `834d6e7` | feat(p11): add institution sandbox ingestion client | `POST /v1/sandbox/complaints/granular` (external-institution-facing, mTLS / OAuth `complaints:write` / HMAC SHA-256 / Idempotency-Key all enforced), `scripts/institution_push_demo.py` CLI sender, `docs/demo/institution-api-workflow.md`. |

Conflict resolution: both branches added the same p10.7 polish
independently; the five conflicted UI files (`page.tsx`,
`CockpitClient.tsx`, `LiveIngestionPanel.tsx`, `en.json`, `es.json`)
were resolved by taking the part-11 side, which already contains the
polish plus the P11A live-ingestion wiring on top of it.

Merge commit: `3ad0efa merge: P11 sandbox completion (P11A + P11A.5a)`.

## Gating blockers closed

### 1. `test_internal_audit::test_audit_post_returns_404_when_secret_not_configured`

The test asserted that `verify_internal_secret` returns 404 when the
shared secret is unset. It was returning 401 because Pydantic
`BaseSettings` reads `.env` from disk, and `monkeypatch.delenv` only
clears `os.environ` — the developer's local `SBS_API_INTERNAL_API_SECRET`
in `.env` survived.

Fix: `tests/test_internal_audit.py` now uses
`monkeypatch.setenv("SBS_API_INTERNAL_API_SECRET", "")`. The
`if not expected:` guard in `_internal_auth.py::verify_internal_secret`
treats both `None` and `""` as "not configured" and returns 404.
Production behaviour unchanged.

### 2. `scripts/demo.sh`

Earlier diagnosis ("`--scale` / `--output-dir` passed to the generator")
was wrong; `demo.sh` already used the right arg names. The actual
failure was that `demo.sh` invoked `uv run python …` and the `uv`
binary was not on this machine's PATH. Stderr was redirected to
`/dev/null`, so the failure surfaced as a generic exit-code-3 from
`fail`.

Fix: `demo.sh` now detects whether `uv` is on PATH and falls back to
`.venv/bin/python` when it isn't. The generator output now goes to
`$OUTDIR/generate.log` instead of being thrown away, so a future
failure shows up.

Verified: `bash scripts/demo.sh --scale small` runs in **~8 s** (3 ×
17 rows, 51 complaints total), three `listener_pass: true` lines,
final `demo.sh: PASS`. See `tmp/demo-run/<latest>/summary.json` for
the per-institution record.

### 3. Next.js typecheck + build

* Stale `.next/types` referenced `src/app/api/ingest/route.js` from
  the part-11 add. `rm -rf app/.next && npm run typecheck` now clean.
* Five `i18next/no-literal-string` errors:
  * **Translated** (real UI copy):
    * `ComplaintCard.tsx` — added `cockpit.complaint_card.{motivo,producto}`
      to both i18n bundles, component now calls `t()`.
    * `ClassificationPanel.tsx` — added `findings.panels.confidence_degraded`
      to both bundles; the panel now reads it via its `labels` prop;
      both call sites (`findings/[id]/page.tsx`, `approvals/[id]/page.tsx`)
      updated.
  * **Scope-disabled with justification comments**:
    * `ClassificationPanel.tsx::span [0, 5]` — technical
      character-index span tag shown to engineers, not regulator copy.
    * `DraftNarrativeEditor.tsx::✓ {savedAt}` — checkmark glyph + an
      already-localised timestamp; no translatable text.
    * `NarrativePanel.tsx::[REDACTED:{r.kind}]` — fixed-format
      redaction token per ADR 0044, machine identifier, not UI copy.

`npm run build` → "Compiled successfully" + the full route table
renders.

## RUC redaction (P11 sandbox completion, exit-gate 1+2 prerequisite)

The P11A commits redacted `pii_name` / `pii_id` (DNI) / `pii_phone` /
`pii_email` / `pii_account`. They did **not** redact RUC (Peruvian
taxpayer id, 11 digits) — a Peruvian-PII payload could carry RUC
through to the canonical complaint.

Added in this prompt:

* `_RUC_PATTERN` and `_detect_ruc` in `api/sbs_api/redaction/engine.py`.
* `pii_ruc` kind threaded through `_build_replacement` and
  `masked_preview` (last 4 digits preserved).
* New enum value `pii_ruc` added to `docs/schemas/agent_run.schema.json`
  (additive; existing rows continue to validate).
* Four new tests in `tests/test_redaction_engine.py`:
  RUC-with-prefix detection, bare-11-digit detection, no swallowing
  of DNI/phone/account when all are present, masked-preview shape.

## Exit gates — evidence

### Gate 1 — institution endpoint accepts the full Peruvian-PII payload

`tests/integration/test_sandbox_granular_api.py::test_granular_full_peruvian_pii_payload_egress`
drives a payload carrying DNI `47291834`, RUC `20512345678`, phone
`+51 987 654 321`, email `carlos.rodriguez@example.com`, name
`Carlos Rodríguez Mendoza`, and card `4556 1234 5678 9999` through
`POST /v1/sandbox/complaints/granular`. **PASS**.

### Gate 2 — redact-before-canonical-storage

Same test asserts: each of the six PII needles appears in
`raw_complaints.raw_narrative`, and none of them appears in
`complaints.description_text`, `agent_runs.tool_calls`,
`agent_runs.final_output`, `audit_events.{action,actor_id,object_id,diff,meta}`,
the HTTP response body, or the cockpit SSE event payload.
`raw_complaints.storage_policy` is `restricted-demo-pii-v1`. **PASS**.

Companion test `test_no_raw_pii_egress.py` extends the assertion to
every row in the four tables, not just the one under test. **PASS**.

### Gate 3 — data-quality checks (partial; honest scope-cut)

The DQ checker (`api/sbs_api/data_quality/checks.py`) validates six
rules: `missing-institution-complaint-id`, `missing-narrative`,
`missing-product` (+ code-list), `missing-motive` (+ code-list),
`missing-channel-operation` (+ code-list), and
`amount-mentioned-without-claim`. DQ results are written to
`audit_events` (action `data-quality-completed`, meta carries error /
warning counts) and to the institution receipt
(`status: accepted | accepted_with_warnings | rejected`).

**Scope-cut — flagged for the next prompt:** the prompt asks for
full Annex 1-A 27-field validation (23 base + 4 bancaseguros) per
Res. SBS 4036-2022. That is 21 additional rules plus the canonical
code lists for each field. The work is purely additive (new DQ rules
do not change the contract), so it is safe to defer; the current
checker covers the high-value rules that drive the demo's
"accepted_with_warnings" and "rejected" paths.

### Gate 4 — audit rows for each stage

`agent_runs` carries one row per submission with the anonymizer
tool_call and the DQ report in `final_output.data_quality`.
`audit_events` carries six rows per submission with kebab-case
actions: `complaint-received`, `taxonomy-normalized`, `pii-redacted`,
`canonical-complaint-persisted`, `data-quality-completed`,
`complaint-triage-emitted`. The demo-ready overlay renamed
`demo-complaint-received` → `complaint-received` and inserted the
`taxonomy-normalized` step. Each row carries `actor_id`,
`created_at`, `object_type`, `object_id`, and a `meta` dict with the
relevant policy versions (`redaction_policy_version`,
`dq_policy_version`) and counts. Verified by
`test_live_ingestion_endpoint.py::test_demo_endpoint_records_five_audit_events`.
**PASS**.

### Gate 5 — cockpit shows the new complaint within ~5 s via SSE

* Programmatic verification (in-process bus capture):
  `test_sandbox_granular_api.py::test_granular_sse_payload_is_pii_free`
  asserts that one `complaint.received` event lands on the `cockpit`
  topic of the in-process SSE bus immediately after the granular
  POST, and that its `data` payload is PII-free. **PASS**.
* Browser-side verification: requires running both servers and
  visually watching the cockpit pick up the card. **Not performed in
  this prompt** (no browser screenshot capability from the harness).
  The walk path is documented below under "Manual browser walk".

### Gate 6 — existing flows preserved

* `pytest -q` against the full suite: **565 passed, 6 skipped**.
* The remaining 3 failures + 20 errors are all `FileNotFoundError:
  'uv'` from `test_demo_determinism` and `test_standards_pack_build`
  — environmental, not P11 regressions, present on this machine
  before the merge.
* `npm run typecheck` (app) and `npm run build` (app) both clean.
* `cd sdk-helpers/typescript && npm test`: **19 / 19 passed**.
* Cockpit + audit/SSE backend completeness:
  `pytest tests/test_cockpit_endpoint.py tests/integration/test_audit_and_sse_completeness.py`:
  **16 / 16 passed**.
* **Browser-side persona switcher / approvals rationale / audit
  pagination / ES↔EN i18n parity: NOT verified by browser in this
  prompt** for the same reason as gate 5. See the manual walk below.

### Gate 7 — BCO-2026-000001 demo invariants

Read directly from the seed script (no merge drift):

* `scripts/seed_demo_narrative.py:456-465` — `composite_score=0.74`,
  `threshold=0.70`, `channel_contributions` `0.30 / 0.20 / 0.25 / …`,
  `anomaly_flag=True`.
* `scripts/seed_demo_narrative.py:321` — `classification:
  "undisclosed-fees-credit"`.
* `scripts/seed_demo_narrative.py:491` — drafted text:
  `"Disputa de cliente sobre comisiones de cuenta."` (deliberately
  omits "comisión por mantenimiento").
* `scripts/dev-seed.sql:169` — `BCO-2026-000001.description_text`
  contains the phrase "comisión por mantenimiento" (the scripted
  edit gap Lucía fills during the demo).

## Manual browser walk (gates 5 + 6 visual portion)

Terminal 1 — API in proxy mode for sandbox local-smoke:

```bash
bash scripts/dev-up.sh
SBS_API_MTLS_MODE=proxy PYTHONPATH="$PWD/api" bash scripts/run-api.sh
```

Terminal 2 — supervisor cockpit:

```bash
cd app && npm run dev
# open http://localhost:3000/supervisor/cockpit
```

Terminal 3 — send a granular complaint with the full PII payload:

```bash
.venv/bin/python scripts/institution_push_demo.py \
    --api-base http://localhost:8000/v1 \
    --profile banco-tier1 \
    --scenario wallet-misclassified \
    --insecure-skip-mtls
```

What to watch in the cockpit:

* Within ~5 s of the CLI's `[6/6] SBS receipt received` line, a new
  card appears on the Tier 1 panel for BANCO_DEMO_001.
* The card carries the **redacted** description (no DNI, no RUC, no
  phone, no email, no name visible — placeholders `<DNI_1>`,
  `<RUC_1>`, `<PHONE_1>`, `<EMAIL_1>`, `<PERSON_1>` instead).
* The supervisor `BCO-2026-000001` anomaly card is unchanged:
  composite 0.74 / threshold 0.70 / channel contributions visible.
* Click into Findings → BCO-2026-000001 → narrative panel: raw
  description carries "comisión por mantenimiento". Draft narrative
  omits it. Editing the draft, saving, and checking the audit
  pagination round-trips an audit row.
* Toggle the persona switcher (Lucía → Sergio → Mariela) — the
  cockpit Tier 1 panel filters change by role-scoping per ADR 0043.
* Toggle locale (es-PE ↔ en-US) — strings flip, no `t()` returns
  the raw key (i18n parity).

> Screenshots for the steps above are **not** captured in this
> prompt. They should be attached to a follow-up when the manual
> walk is run.

## What's deferred (next prompt)

* **Annex 1-A 27-field DQ.** 21 more rules + canonical code lists.
* **Model-provider abstraction.** `ModelProvider` interface and the
  OnPrem / Cloud / Replay / Mock implementations; the agent
  orchestration loop.
* **BETO classifier, summarization, live anomaly composite, seed
  regeneration via real models.** All still seeded.
* **Browser walk + screenshots** for the cockpit-side persona
  switcher / approvals rationale / i18n parity.
* **Tag `p11-sandbox-close`.** Holding the tag until the browser
  walk produces the missing screenshots and the deferred 27-field
  DQ work lands.

## Test commands (the green ones, copy-pasteable)

```bash
# Backend unit + integration (565 passed, 6 skipped; 3 fail + 20 err
# are uv-not-on-PATH environmental, unrelated to P11).
PYTHONPATH=$PWD/api .venv/bin/pytest -q

# P11 / P11A / P11A.5a subsets in isolation (all green):
PYTHONPATH=$PWD/api .venv/bin/pytest \
    tests/test_redaction_engine.py \
    tests/integration/test_live_ingestion_endpoint.py \
    tests/integration/test_no_raw_pii_egress.py \
    tests/integration/test_sandbox_granular_api.py \
    tests/integration/test_institution_push_demo.py \
    tests/test_internal_audit.py \
    tests/test_cockpit_endpoint.py \
    tests/integration/test_audit_and_sse_completeness.py -q

# Demo path:
bash scripts/demo.sh --scale small    # ~8 s, 3 × 17 rows, 3 listener_pass=true

# Frontend:
( cd app && rm -rf .next && npm run typecheck && npm run build )

# SDK helpers:
( cd sdk-helpers/typescript && npm test )    # 19 / 19
```

## Browser walk verification — 2026-05-26

Verified manually by Oumaïma against running API + frontend.

Auth chain: mTLS proxy + OAuth + HMAC + Idempotency-Key enforced on submission.
Two-tier ingestion: Tier 1 NRT (BANCO_DEMO_001) and Tier 2 batch (COOPAC_DEMO_002) both produce identical canonical Annex 1-A records.
Redaction: response and UI show <PERSON_1>, <DNI_1>, <PHONE_1>, <EMAIL_1>, <ACCOUNT_1> tokens.
Storage split confirmed at DB layer: raw_complaints holds raw narrative with storage_policy=restricted-demo-pii-v1; complaints (canonical) holds redacted narrative. FK join via canonical_complaint_id shows raw_chars=273 vs canonical_chars=221 — proof of redaction at storage.
27-field Annex 1-A DQ validator firing (DQ-A1A-007/009/010/013/016 observed).
10-event kebab-case audit chain persisted per submission.

Screenshots: screenshots/2026-05-26-p11-walk/.
