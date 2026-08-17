# Handover audit — sbs-peru-sandbox

- **Date:** 2026-08-10
- **Branch:** `oss-release-pr` @ `d38e22b` (working tree clean before and after this audit)
- **Scope:** read-only, evidence-based. No tracked file was modified; nothing committed.
- **Method:** every claim below is backed by a verbatim command + output in the
  Evidence appendix (§E). Claims that could not be runtime-verified are in §UNVERIFIED.

---

## (a) Executive summary

1. The **auth chain is real and works end-to-end**: mTLS + OAuth client-credentials
   (cert-bound `cnf.x5t#S256`) + HMAC-SHA256 + replay rejection + rate limiting all pass
   against a live stack (E1.6, E3.1).
2. **Tier 1 `POST /v1/complaints` does not run any agent.** The agent pipeline has no
   call site on that route; `SBS_API_AGENTS_PIPELINE_ENABLED` is read in exactly one
   place, on the demo-ingestion path only (E3.4, E3.5).
3. Agents **are** reachable through the real auth chain via
   `POST /v1/sandbox/complaints/granular`, which is **absent from the canonical OpenAPI
   contract** (E3.9, E3.10).
4. **Triage / Investigation / Synthesis are REAL** (real tool calls, live DB reads,
   auditable `agent_runs` rows) — but every model call was served by **MockProvider via
   the on_prem fallback**, logged as "demo-safe but not regulator-grade" (E3.6, E3.11).
5. **DIValeVale, Reclamito, Lupaman, Insight-Chatbot are not wired.** DIValeVale's only
   non-test caller is itself only called by tests; the other three exist solely as
   registry entries (E3.12, E3.13).
6. **4 of 6 stage gates and both composite gates fail**, with one reproducible root
   cause: 9 ORM model modules are missing from `db/models/__init__.py` (E2.2, E2.5).
7. The **full suite passes (736 passed)** — it only passes when run whole, which masks
   the gate failures (E2.4).
8. **README step 2 is broken on any machine with a `.env`**: `run-api.sh` sources `.env`
   *after* the caller's exports, silently overriding them (E1.4).
9. **Annex 1-A drift confirmed**: the UI tab titled "27 campos / 27 fields" renders a
   28-row table (E5.1). No `bancaseguros_nombre` field exists anywhere (E5.3).
10. **Verdict: not ready to hand over as-is.** 5 P0s below; each is small and specific.

---

## (b) Agent reality table

The audit brief's `REAL` criterion names LangGraph. **ADR 0001 explicitly rejects
LangGraph** in favour of an in-house tool-calling loop, and `langgraph` is not a
dependency and not imported anywhere (E3.2). The criterion is therefore applied on
substance — *real tool calls against live services, triggered through the public API
path* — not on the framework name.

The brief also names "five agents (Triage, Investigation, Cockpit, + 2 scaffolds)".
That matches neither artifact in the repo: **ADR 0001 names 5** (triage, investigation,
synthesis, taxonomy-harmonizer, cross-source-correlator) and the **locked registry
names 6, with a different membership** (divalevale, reclamito, lupaman, triage,
investigation, insight-chatbot). There is no "Cockpit" agent. The table covers the
union of both lists.

| Agent | Classification | Provider serving model calls | Evidence |
|---|---|---|---|
| **triage** | **REAL** — 3 real tool calls (`query_dq_results`, `query_taxonomy_normalizations`, `classify_complaint`) against live Postgres; auditable `agent_runs` row; reachable through the full auth chain via the granular sandbox route | `OnPremProvider` → **fell back to MockProvider** (vLLM unreachable) | E3.6, E3.7, E3.9, E3.11 |
| **investigation** | **REAL** — real DB-backed `similar_complaints` (5 live rows), anomaly composite, narrative draft; auditable run. Not reached automatically on this record (triage routed `info-only`); invoked directly to verify | `OnPremProvider` → **MockProvider** fallback | E3.8, E3.11 |
| **synthesis** | **REAL** — real audit-trail reads, structured executive summary; auditable run | `OnPremProvider` → **MockProvider** fallback | E3.8, E3.11 |
| **cross-source-correlator** | **REPLAY** — `ReplayProvider` fixtures; skipped silently when no fixture exists. Load-bearing (feeds cockpit strip + approval bundle) per `tests/cleanup/test_no_scaffold_agents.py` | ReplayProvider | E3.3, E3.14 |
| **divalevale** (DIValeVale) | **SCAFFOLD** — implemented and unit-tested, but its only non-test caller is `ingestion/pipeline.py`, whose only callers are tests. Zero `validation_audit` rows; absent from the live pipeline timeline | n/a — never invoked at runtime | E3.12, E3.9 |
| **reclamito** (`issue-resurface`) | **SCAFFOLD** — appears only in `registry.py`. No implementation module, no runs | n/a | E3.13 |
| **lupaman** (`peer-risk-radar` + `sector-broadcast`) | **SCAFFOLD** — appears only in `registry.py` and `status.py`. No runtime, no runs | n/a | E3.13 |
| **insight-chatbot** | **SCAFFOLD** — appears only in `registry.py`. No implementation module, no runs | n/a | E3.13 |
| **taxonomy-harmonizer** (ADR 0001) | **REMOVED** — deliberately deleted; enforced by a cleanup test | n/a | E3.3 |
| **live-ingestion-orchestrator** | **REAL** — writes its own `agent_run` (status `partial`) on the demo/sandbox path | n/a (no model call) | E3.11 |

**Every model call observed in this audit was served by `MockProvider`**, reached
through `OnPremProvider`'s silent fallback. The exact log line is in E3.11.

---

## (c) Findings

### P0 — blocks vendor handover

**P0-1 — 9 ORM models are missing from the metadata registry; 4 of 6 stage gates and both composite gates fail.**
`api/sbs_api/db/models/__init__.py` imports 18 model modules but 9 exist on disk and are
not imported: `digest_audit`, `fi_brand_alias`, `fi_circuit_breaker`,
`incident_annotation`, `indecopi_case`, `manual_finding`, `pattern_detection`,
`social_signal`, `validation_audit` (E2.5). The `db_schema` fixture builds the test
schema with `Base.metadata.create_all` *after* importing that package, so those tables
are never created; `conftest.py:251` then imports `FIBrandAlias` directly and seeds it,
which errors (E2.2, E2.6). Result: `stage-a`, `stage-b`, `stage-c`, `stage-d`,
`stage-g-contract` and `stage-g-full` all fail (E2.1, E2.3).
Second-order hazard: that `__init__.py`'s own docstring says the eager import exists so
"Alembic's autogenerate sees the full metadata graph". With 9 models invisible, a vendor
running `alembic revision --autogenerate` can emit a migration that **drops 9 live
tables**.

**P0-2 — `stage-g-full` never reaches its live-stack assertion.**
The gate runs `stage-g-contract` first and aborts on its failure, so the only part of
the gate that is actually a *full* (live-stack) check is skipped. Run standalone, that
component passes (E2.7). Today the gate reports failure without ever having exercised
the live path it exists to exercise.

**P0-3 — Tier 1 `POST /v1/complaints` runs no agent at all.**
The route has no agent call site (E3.4). `settings.agents_pipeline_enabled` is read in
exactly one place — `demo_ingestion/orchestrator.py:796` (E3.5). A complaint submitted
through the canonical Tier 1 path with `SBS_API_AGENTS_PIPELINE_ENABLED=true` produced
**zero** `agent_runs` rows (E3.3, E3.5). The `Settings.agents_pipeline_enabled`
docstring — "the live-ingestion orchestrator triggers the Part 12 chain after canonical
complaint persistence" — does not describe the Tier 1 route.

**P0-4 — The only API path that runs agents is undocumented.**
`POST /v1/sandbox/complaints/granular` carries the full auth chain (mTLS + OAuth + HMAC)
and drives the whole pipeline including agents (E3.9), but the string `sandbox` does not
appear as a path in `api/openapi/sbs-api-v1.yaml` (E3.10). ADR 0027 makes that YAML the
canonical contract, and `/docs`/`/redoc` are disabled — so a vendor reading the contract
cannot discover the only route that exercises the agent layer.

**P0-5 — `DIValeVale` is documented as mandatory and is not in any runtime path.**
`ingestion/pipeline.py` states "DIValeVale validation is the FIRST stage — every Tier-1
record passes through it before Triage." Its only non-test caller is that module, whose
only callers are tests (E3.12). The live pipeline timeline for a real submission shows
`schema_validated → taxonomy_normalized → pii_redacted → canonical_complaint_persisted →
… → agent_pipeline_completed` with **no DIValeVale stage** (E3.9), and
`validation_audit` holds 0 rows (E3.12).

### P1 — vendor will trip on it

**P1-1 — `scripts/run-api.sh` silently overrides caller-exported env vars.**
The script does `set -a; . ./.env; set +a` *after* the caller's exports, so `.env` wins.
On this machine, the README's literal step 2
(`SBS_API_MTLS_MODE=direct … bash scripts/run-api.sh`) yields `mtls_mode=proxy` — the
API starts on plain HTTP and `scripts/smoke-test-auth.sh` (which requires
`https://…:8443`) cannot pass (E1.4). Note this is a *shell* precedence bug, not a
Pydantic one: `Settings` resolves exported env vars **over** `.env` correctly (E1.3).
A fresh clone with no `.env` is unaffected; the trap fires the moment a vendor puts any
`SBS_API_*` var in `.env`, which `.env.example` invites them to do.

**P1-2 — README's 3-command bootstrap never starts the cockpit or Keycloak.**
`dev-up.sh` brings up **postgres + redis only** (E6.1). The supervisor cockpit — the
README's headline screenshot — needs Keycloak (for the persona session) and
`npm install && npm run dev` in `app/`, plus `app/.env.local` derived from
`app/.env.example`, and `SBS_API_INTERNAL_API_SECRET` set to the *same* value in the
FastAPI process. None of that is in the README (E6.2).

**P1-3 — The one document that does explain the UI gives the wrong URL.**
`docs/demo/institution-api-workflow.md:162` says the cockpit is at
`http://localhost:3000/supervisor`. That 404s; `(supervisor)` is a Next.js route group,
not a URL segment. The real URL is `http://localhost:3000/app/cockpit` (E6.3).

**P1-4 — Which provider served a model call is not persisted.**
`agent_runs` has no `model_provider` column (E3.15). ADR 0001's stated contract is that
"every reasoning step must be reconstructable from the database without re-running the
model", yet the fact that MockProvider — not a real model — produced an output survives
only in process stderr (E3.11). A vendor reading the DB cannot tell a real inference
from a mock.

**P1-5 — `SBS_API_MODEL_PROVIDER` is read via `os.getenv`, not through `Settings`.**
`providers/__init__.py:91` reads it directly, so it is honoured only by processes whose
environment actually carries it. `run-api.sh` exports `.env` so it works there; the arq
worker container and `scripts/run_agent_pipeline_on_new.py` do not source `.env`, so the
same `.env` line silently does nothing for them (E1.5, E3.16). The `Settings` field that
*is* wired (`agents_pipeline_provider`, env var `SBS_API_AGENTS_PIPELINE_PROVIDER`) is
not mentioned in `.env.example`, which documents only `SBS_API_MODEL_PROVIDER`.

**P1-6 — Root `.env.example` omits `SBS_API_INTERNAL_API_SECRET`.**
It is required for the Next.js → FastAPI internal channel and is documented only from
the UI side, in `app/.env.example` (E6.4). A vendor configuring the API from the root
example will have a cockpit whose internal calls are rejected.

**P1-7 — Cockpit data routes shell out to a hard-coded `.venv` path.**
`app/src/app/api/journey/*/route.ts` spawns `<repo>/.venv/bin/python scripts/…py`,
resolving the repo as `process.cwd()/..` (E4.4). This breaks if the vendor's uv
environment is not at `./.venv`, or if `next` is started from anywhere but `app/`.
These routes returned live data here only because that layout happened to hold.

**P1-8 — `app/README.md` is stale.**
It says "Five screens" and lists a directory tree without the `(supervisor)` route
group; there are ~20 page routes, including `analytics`, `ingestion`, `processing`,
`assistant`, `admin`, `docs`, `sandbox`, `rr1`, `demo-journey`, `developers` and the
`fi/*` surfaces (E4.1, E6.5).

### P2 — polish

**P2-1 — Annex 1-A field-count drift (28 rendered under a "27 fields" heading).**
See §(e-schema) below and E5.1.

**P2-2 — `classify_complaint` can never match a real submission.**
Its rules table is keyed on `("credit-card", "undisclosed-fee")`-style values, but the
API's enums are `TARJETA_CREDITO` / `COBRO_INDEBIDO` (E3.17). Every real Tier 1 record
therefore classifies as the default `other` @ 0.55 — which is exactly what the audited
submission produced (E3.6). The demo complaint `BCO-2026-000001` is hard-coded to return
`undisclosed-fees-credit` @ 0.87 with `model_id: beto-replay-v1`. No BETO model is
invoked anywhere.

**P2-3 — `rank_features` ("feature importance / XGBoost") is a constant.**
Non-demo complaints always receive the same three-item `DEFAULT_FEATURES` list under
`feature_model_id: xgboost-replay-v1` (E3.18). Confirmed in the live output (E3.8).

**P2-4 — Placeholder leaks into a generated narrative.**
The investigation draft rendered `clasificación inicial '—'` for a real complaint
(E3.8) — the em-dash placeholder ADR 0001 describes as the pre-Part-12 state.

**P2-5 — `.env` first line is a stray instruction.**
`.env` begins `# Open .env in your editor and replace its contents with:` — a
copy-paste artifact from the setup docs (E1.2). `.env` is correctly gitignored (E1.2),
but it holds a live-looking Azure OpenAI key; confirm it is not shipped with the
handover bundle.

**P2-6 — Keycloak's healthcheck reports `unhealthy` while the realm serves 200.**
Confirmed as a false negative, as the brief anticipated (E1.6). Worth fixing before
handover so a vendor does not chase it.

**P2-7 — Dev server redirects to `http://0.0.0.0:3000`.**
`/app/api/auth/demo-login` issues a `Location: http://0.0.0.0:3000/app/cockpit`, which
drops cookies for any client that treats the host as different (E4.2). Browsers on the
same origin cope; scripted clients do not.

**P2-8 — `/api/aggregates/social` degrades to sample data.**
It returned `{"available": false}` for the supervisor persona (role-gated to
`sbs:sbs_it`), and the UI falls back to a static sample set (E4.3). The fallback is
honestly badged "datos de muestra / sample data" in the UI (E4.5) — noted as a credit,
not a defect.

---

## (d) §2 — Test gates: what exists, what was run, banned patterns

The brief asks for `stage-N-contract` / `stage-N-full`. **No such targets exist.** The
gates are lettered, defined in `scripts/smoke-test-batch.sh`: `stage-a` … `stage-f`,
`stage-g-contract`, `stage-g-full`. `Makefile: smoke` runs `stage-g-full` (E2.0).
`tests/test_demo_determinism.py:26-28` references a **`stage-h-full` / `stage-h-contract`
pair that is not implemented** — the runner's own error message lists valid stages and
stops at `stage-g-full` (E2.0).

| Gate | Exit | Result |
|---|---|---|
| `stage-a` | 1 | **FAIL** — 9 passed, 1 error |
| `stage-b` | 1 | **FAIL** — 6 passed, 1 error |
| `stage-c` | 1 | **FAIL** — 6 passed, 1 error |
| `stage-d` | 1 | **FAIL** — 26 passed, 1 error |
| `stage-e` | 0 | PASS — 8 passed |
| `stage-f` | 0 | PASS — 25 passed |
| `stage-g-contract` | 1 | **FAIL** — 83 passed, 1 error |
| `stage-g-full` | 1 | **FAIL** — aborted at contract; live check skipped |
| `stage-g-full` live component, standalone | 0 | PASS — accepted=3, rejected=0, listener PASS |
| `uv run pytest -q` (whole suite) | 0 | PASS — 736 passed, 6 skipped |

**Banned-pattern grep.** The only path exclusive to a FULL gate is
`scripts/smoke_stage_g_live.py`: **zero hits** for `MockTransport`, `TestClient`,
`ASGITransport`, `dependency_overrides`, `mock.patch` (E2.8). **No P0 finding on this
axis.**

One caveat, reported for completeness rather than as a violation: `stage-g-full` is
defined as `stage-g-contract` + the live check, so it transitively executes contract
tests that do use the banned patterns (`test_webhook_delivery.py` 5 hits,
`test_fixture_conformance.py` 5, `test_batch_endpoint.py` 1, `test_batch_status_endpoint.py`
1, `test_webhook_url_validation.py` 1 — E2.9). The script documents this explicitly
("runs … against the live testcontainer Postgres + httpx MockTransport"), and contract
stages are exempt per the brief, so this is disclosed composition, not concealment.

---

## (e) §5 — Annex 1-A schema conformance

**Confirmed clean:** no `bancaseguros_nombre` field exists anywhere in the repository
(E5.3). The four bancaseguros fields are `bancaseguros` (trigger) +
`producto_bancaseguros`, `motivo_bancaseguros`, `submotivo_bancaseguros` (conditional),
matching the 1-trigger + 3-conditional shape (E5.2).

**Drift found (P2-1).** `app/src/components/docs/DocsTabs.tsx` renders a table titled
`Anexo 1-A · Res. SBS 4036-2022 · 27 campos / 27 fields` that contains **28 rows**
(E5.1). The DQ rules number the bancaseguros conditionals as *campos 25 / 26 / 27*
(E5.4), which puts the trigger at campo 24 and implies **23 base fields**. The 28-row
table therefore carries one field too many. The 28-column layout also appears in
`scripts/ingest_sample_dataset.py` `_COL_INDEX` (indices 0–27, E5.5).

Inferred, not documented: the extra row is `EMPRESA` (reporting entity), which the API
derives from the OAuth token and mTLS subject rather than the payload — excluding it
gives exactly 23 base + 4 bancaseguros = 27. See §UNVERIFIED.

Separately and *not* a contradiction: ADR 0026 defines a **15-field curated subset** for
the sandbox submission surface, which is what the Tier 1/Tier 2 CSV actually carries
(E5.6). The 27-field figure describes the DQ rule surface, not the wire format. A vendor
reading only the README ("data-quality validation against the 27-field Annex 1-A
schema") and then the 15-column golden CSV will need that explained.

---

## (f) §4 — UI wiring

20 supervisor/FI routes were fetched against the live backend with a real Keycloak-backed
demo session. **All 20 returned HTTP 200** (E4.1). "Live" below means the page's data was
verifiably produced by the running stack; the decisive test is whether the records
submitted during this audit (`BCO-2026-598556` Tier 1, `COP-2026-737757` Tier 2) appear
in the rendered output.

| View | Backend calls on SSR | Verdict |
|---|---|---|
| `/app/cockpit` | 2 | **LIVE** — renders **both** the Tier 1 and the Tier 2 record submitted in this audit (E4.6) |
| `/app/findings` | 1 | **LIVE** — renders both audited records (E4.6) |
| `/app/audit` | 1 | **LIVE** — 7 audit rows for the audited Tier 1 record (E4.6) |
| `/app/approvals` | 1 | **LIVE** — `internalGet` server fetch (E4.7) |
| `/app/cockpit/aggregates` | 0 (client-side) | **LIVE** — `/api/aggregates/trend`, `patterns`, `sources`, `feed` each proxy to the backend; `feed` returned real complaint rows (E4.3) |
| `/app/analytics`, `/app/queue`, `/app/processing`, `/app/assistant`, `/app/admin`, `/app/sandbox`, `/app/demo-journey`, `/app/fi/*` | 0 (client-side) | **LIVE via client fetch** — all 23 client fetch targets are `/app/api/*` BFF routes; `/api/admin/audit` proxies to the backend, `/api/journey/*` query Postgres via `scripts/cockpit_stats.py` (E4.3, E4.4, E4.8) |
| `/app/rr1` | 0 | **STATIC** — renders `@/lib/rr1-2025.json` (E4.9) |
| `/app/ingestion` | 0 | **STATIC** — renders `@/lib/journey-emails.json` (E4.9) |
| `/app/demo-journey`, `/app/fi/banco-demo-001/inbox` | 0 | **PARTLY STATIC** — import `@/lib/golden-complaint.json` alongside live fetches (E4.9) |
| `/app/docs`, `/app/developers`, `/app/developers/credentials` | 0 | **STATIC by design** — documentation surfaces |
| Social / INDECOPI / SBS-DSC tables (`components/persona/*`) | 0 | **STATIC sample**, explicitly badged "datos de muestra / sample data" (E4.5) |

---

## (g) §6 — Handover readiness inventory

| Item | State |
|---|---|
| `scripts/dev-up.sh` | **Works** — exit 0, migrations + seeds + dev CA + oauth clients (E6.1). Starts postgres + redis only. |
| README step 2 (`run-api.sh`) | **Breaks with a `.env` present** — P1-1 (E1.4) |
| README step 3 (`smoke-test-auth.sh`) | **Passes** when the API is started with the right env directly — all 5 assertion groups (E1.6) |
| Cockpit startup instructions | **Missing from README** — P1-2; the one doc that has them has the wrong URL — P1-3 |
| ADRs | **30 files, index complete and accurate.** All 30 on-disk ADRs are listed in `docs/adr/README.md`; the 15 gaps (0002–0015, 0024) are `Proposed (queued, not yet written)` by design (E6.6). README's "current head: ADR 0045" is correct. |
| **ADR 0001** | **Current and honest.** Status Accepted; explicitly supersedes its own MCP/A2A/LangGraph proposal in favour of the in-house loop; the slug is retained deliberately to preserve the anchor (E3.2). Its agent roster (5 agents) has since drifted from the locked registry (6, different membership) — worth one paragraph before handover. |
| `.env.example` (root) | **Exists; incomplete** — omits `SBS_API_INTERNAL_API_SECRET` (P1-6); documents `SBS_API_MODEL_PROVIDER` but not the wired `SBS_API_AGENTS_PIPELINE_PROVIDER` (P1-5) |
| `app/.env.example` | **Exists and is accurate** — Keycloak, internal API base URL + secret, demo toggles (E6.4) |
| Seed scripts | **Present and documented** — `dev-seed.sql` (institutions, HMAC secrets, demo complaints), `seed-oauth-clients.sh` (argon2id), `dev-ca.sh` + `seed-certificates.sql`, all invoked by `dev-up.sh` and listed in its header (E6.1). Sandbox HMAC secrets are well-known constants and are labelled as such in the SQL. |
| `git status` | Clean at start and at end of this audit (E1.1, E7.1) |

---

## §UNVERIFIED

| Item | Reason |
|---|---|
| Which specific field is the 28th/extra one in the Annex 1-A table | No document in the repo states the authoritative 27-field list. `EMPRESA` is a strong inference (it is derived from auth, not payload, and excluding it yields exactly 23+4) but is not written down anywhere. |
| Behaviour of any agent under a **real** `OnPremProvider` (vLLM) or `ReplayProvider` | No vLLM endpoint is reachable in this environment; every run fell back to MockProvider. Replay fixtures exist only for the demo complaint `BCO-2026-000001`. |
| Whether `run-api.sh`'s `.env` override affects a **fresh vendor clone** | Depends on what the vendor puts in `.env`, which does not exist on a fresh clone. Verified only against this machine's `.env`. |
| `stage-h-contract` / `stage-h-full` | Referenced in `tests/test_demo_determinism.py` but not implemented in the runner; nothing to execute. |
| Browser-rendered behaviour of the cockpit (charts, SSE, interactions) | Verified by HTTP fetch + backend-log correlation + record matching, not by a real browser. Client-side render errors after hydration would not be visible to this method. |
| `scripts/demo.sh` end-to-end | Not run. Note for the record: its batch driver `scripts/demo_replay.py` **bypasses the HTTP API entirely** — it INSERTs the `batches` row and enqueues arq directly (E6.7), so it does not exercise the auth chain. |
| Cross-source-correlator output quality | Only one historical `agent_runs` row exists (2026-07-13) and no replay fixture matched the audited complaints, so it was skipped at runtime. |
| Whether the 9 unregistered models would actually be dropped by `alembic --autogenerate` | The mechanism is documented in the `__init__.py` docstring and the omission is verified; generating a migration would have written a file, which the read-only constraint forbids. |

---

## (h) Evidence appendix

### E1 — Environment & config

**E1.1 — repo state (start)**
```
$ git status && git rev-parse --abbrev-ref HEAD && git log --oneline -15
On branch oss-release-pr
Your branch is up to date with 'origin/oss-release-pr'.

nothing to commit, working tree clean
oss-release-pr
d38e22b docs: use maintainer contact in SECURITY.md pending shared mailbox
59ecaed fix(ui): classify info-only routed complaints as completed; render skipped stages without spinners
cb7bc42 docs: replace cockpit screenshot
2894161 docs: add cockpit screenshot asset
8c27849 docs: add cockpit screenshot to README
ba85a86 chore(oss): current-year LICENSE, consolidate CONTRIBUTING to root
961d449 chore(oss): replace demo persona names with role aliases; clean fictional-name and parenthetical artifacts
39e04a8 fix(tests): schema-wide reset in db_schema so migration-created tables cannot poison later fixtures
3ec28a5 fix(tests): restore pgvector extension after schema-wide drop in migration test
81f8c26 fix(errors): add missing CircuitBreakerPaused exception (SBS-503-004) + error-catalog entry
a64c00b fix: wire persona stub into oauth dep, enforce tier-1 circuit breaker, seed webhook/alias/social fixtures in conftest
f406c70 chore(oss): drop second hygiene TODO and dangling catalog fragment
9c93977 chore(oss): remove stray file and scrub session reference from error catalog
67aa364 fix(ci): restore parameterized standards-pack workflow; drop cut v0.2.0 bump tests
2b4a65f chore(oss): scrub remaining internal references (ADR owner labels, templates, setup docs)
```
Uncommitted files: none.

**E1.2 — `.env` (values redacted, names kept) + ignore status**
```
$ sed -E 's/(SECRET|PASSWORD|KEY|TOKEN|SALT|PASS)([A-Z_]*)=.*/\1\2=<REDACTED>/I' .env
# Open .env in your editor and replace its contents with:
AZURE_OPENAI_API_KEY=<REDACTED>
AZURE_OPENAI_ENDPOINT=https://comp…<redacted:azure-endpoint>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-5.4
AZURE_OPENAI_API_VERSION=2024-06-01
GITHUB_REMOTE=origin
SBS_API_INTERNAL_API_SECRET=<REDACTED>
SBS_API_MTLS_MODE=proxy
#SBS_API_PROXY_URL=http://localhost:8080
#SBS_API_PROXY_USERNAME=proxyuser
#SBS_API_PROXY_PASSWORD=<REDACTED>

$ git check-ignore -v .env .env.local .demo-internal-api-secret
.gitignore:119:.env	.env
.gitignore:120:.env.local	.env.local
.gitignore:96:.demo-internal-api-secret	.demo-internal-api-secret
```
Note: `.env` sets **none** of `SBS_API_MODEL_PROVIDER`, `SBS_API_CLOUD_LEGAL_APPROVED`,
`SBS_API_AGENTS_PIPELINE_ENABLED`.

**E1.3 — effective config, and the brief's precedence premise tested**
```
$ .venv/bin/python -c "... from sbs_api.config import Settings; s=Settings(); print(...)"
mtls_mode = 'proxy'
agents_pipeline_provider = 'on_prem'
agents_pipeline_enabled = False

$ SBS_API_MTLS_MODE=direct .venv/bin/python -c "..."
exported os.environ = direct
effective mtls_mode = 'direct'
```
The three values the brief asks for, as they resolve on this machine:
- `SBS_API_MODEL_PROVIDER` — **not set** anywhere. Resolution falls through
  `os.getenv` → `Settings.agents_pipeline_provider` → **`on_prem`** (default).
- `SBS_API_MTLS_MODE` — **`proxy`** (from `.env`).
- `SBS_API_CLOUD_LEGAL_APPROVED` — **not set** → cloud provider gated off.

The brief states ".env silently overrides CLI-exported vars, so .env IS the effective
config." For **Pydantic `Settings` that is false** — the exported var wins, as shown
above. It is **true for anything launched through `scripts/run-api.sh`**, for the shell
reason in E1.4.

**E1.4 — the real override mechanism (`run-api.sh`)**
```
$ bash -c 'export SBS_API_MTLS_MODE=direct SBS_API_AUTH_STUB_ENABLED=false
echo "caller exported: SBS_API_MTLS_MODE=$SBS_API_MTLS_MODE SBS_API_AUTH_STUB_ENABLED=$SBS_API_AUTH_STUB_ENABLED"
set -a; . ./.env; set +a
echo "after sourcing .env: SBS_API_MTLS_MODE=[$SBS_API_MTLS_MODE] SBS_API_AUTH_STUB_ENABLED=[$SBS_API_AUTH_STUB_ENABLED]"'
caller exported: SBS_API_MTLS_MODE=direct SBS_API_AUTH_STUB_ENABLED=false
after sourcing .env: SBS_API_MTLS_MODE=[proxy] SBS_API_AUTH_STUB_ENABLED=[false]
```
`scripts/run-api.sh` performs exactly this `set -a; . ./.env; set +a` before applying its
`${VAR:-default}` fallbacks, so `direct` becomes `proxy` and the `if [[ … == "direct" ]]`
TLS branch is never taken.

**E1.5 — `SBS_API_MODEL_PROVIDER` is read outside `Settings`**
```
$ grep -rn "SBS_API_MODEL_PROVIDER" api/
api/sbs_api/config.py:338:            "SBS_API_MODEL_PROVIDER. The on_prem provider falls back to "
api/sbs_api/agents/__init__.py:12:provider is selected via the ``SBS_API_MODEL_PROVIDER`` environment
api/sbs_api/agents/providers/__init__.py:91:        or os.getenv("SBS_API_MODEL_PROVIDER")
```

**E1.6 — stack state and genuine reachability**
```
$ docker compose ps --format 'table {{.Name}}\t{{.Service}}\t{{.Status}}\t{{.Ports}}'
NAME                   SERVICE            STATUS                         PORTS
sbs-keycloak           keycloak           Up About an hour (unhealthy)   0.0.0.0:8081->8080/tcp
sbs-postgres           postgres           Up About an hour (healthy)     0.0.0.0:5432->5432/tcp
sbs-redis              redis              Up About an hour (healthy)     0.0.0.0:6379->6379/tcp
sbs-webhook-listener   webhook-listener   Up About an hour               0.0.0.0:8080->8080/tcp
sbs-worker             worker             Up About an hour

$ curl -s http://localhost:8081/realms/sbs-demo/.well-known/openid-configuration | head -c 200
{"issuer":"http://localhost:8081/realms/sbs-demo","authorization_endpoint":"http://localhost:8081/realms/sbs-demo/protocol/openid-connect/auth","token_endpoint":"http://localhost:8081/realms/sbs-demo/

$ curl -s -o /dev/null -w '%{http_code}' .../openid-configuration   → 200
$ psql -tAc "select 'postgres -> ok, complaints='||count(*) from complaints;"
postgres -> ok, complaints=98
$ docker exec -i sbs-redis redis-cli PING   → PONG
$ docker logs sbs-worker | tail -1
recording health: Aug-10 18:21:41 j_complete=57 j_failed=0 j_retried=0 j_ongoing=0 queued=0
```
Keycloak's `unhealthy` is a **false negative**, exactly as the brief anticipated: the
realm's discovery document serves 200.

Docker was not running at audit start; the daemon was started and
`docker compose up -d` brought the stack up (permitted by the brief).

`scripts/smoke-test-auth.sh`, with the API started directly (bypassing `run-api.sh`):
```
$ bash scripts/smoke-test-auth.sh ; echo "exit=$?"
==> 0. liveness via mTLS
  mTLS handshake + liveness OK
==> 1. POST /v1/oauth/token
  got OAuth token (length=429)
  cnf.x5t#S256 binding OK
==> 2. signed POST /v1/complaints
  201 Created OK
  X-RateLimit-Limit=1000 Remaining=999
==> 3. replay rejection
  SIGNATURE_REPLAYED OK
==> 4. rate-limit exhaustion (override → 3/min)
  429 + 4 rate-limit headers OK
All auth-chain smoke-test assertions passed.
exit=0
```

### E2 — Test gates

**E2.0 — gate inventory**
```
$ grep -n "stage-" scripts/smoke-test-batch.sh | tail -1
199:    fail "Unknown stage: $STAGE. Valid: stage-a stage-b stage-c stage-d stage-e stage-f stage-g-contract stage-g-full"
$ grep -n "stage-h" tests/test_demo_determinism.py
26:live-stack exit gate (stage-h-full) is exercised by
28:log; this test is the contract-level companion (stage-h-contract).
$ grep -n "smoke" Makefile
14:	@echo "  smoke          — run scripts/smoke-test-batch.sh stage-g-full"
30:	bash scripts/smoke-test-batch.sh stage-g-full
```

**E2.1 — stage-a … stage-f**
```
########## stage-a ##########
exit=1
ERROR tests/test_batch_endpoint.py::test_post_batch_returns_202_with_location
9 passed, 1 warning, 1 error in 4.73s
FAIL: stage-a pytest assertions did not pass
########## stage-b ##########
exit=1
ERROR tests/test_batch_worker.py::test_process_batch_happy_path - sqlalchemy....
6 passed, 1 error in 3.63s
FAIL: stage-b pytest assertions did not pass
########## stage-c ##########
exit=1
ERROR tests/test_batch_status_endpoint.py::test_status_visible_immediately_after_upload
6 passed, 1 error in 4.04s
FAIL: stage-c assertions did not pass
########## stage-d ##########
exit=1
ERROR tests/test_webhook_delivery.py::test_delivery_happy_path - sqlalchemy.e...
26 passed, 1 error in 4.89s
FAIL: stage-d assertions did not pass
########## stage-e ##########
exit=0
8 passed in 0.18s
stage-e: PASS
########## stage-f ##########
exit=0
25 passed in 0.30s
stage-f: PASS
```

**E2.2 — the single root cause**
```
E   asyncpg.exceptions.UndefinedTableError: relation "fi_brand_aliases" does not exist
E   sqlalchemy.exc.ProgrammingError: ... relation "fi_brand_aliases" does not exist
E   [SQL: INSERT INTO fi_brand_aliases (institution_id, alias_normalized, alias_kind) ...]
E   [parameters: ('SBS-001234', 'banco demo', 'display', 'SBS-001234', 'bancodemo', 'handle', 'SBS-001234', 'bcodemo.pe', 'domain')]
```

**E2.3 — composite gates**
```
########## stage-g-contract ##########
exit=1
ERROR tests/test_batch_endpoint.py::test_post_batch_returns_202_with_location
83 passed, 1 warning, 1 error in 9.83s
FAIL: stage-g-contract pytest assertions did not pass

########## stage-g-full ##########
exit=1
ERROR tests/test_batch_endpoint.py::test_post_batch_returns_202_with_location
83 passed, 1 warning, 1 error in 9.70s
FAIL: stage-g-contract pytest assertions did not pass
FAIL: stage-g-contract failed; live-stack check skipped
```

**E2.4 — whole suite passes**
```
$ uv run pytest -q
736 passed, 6 skipped, 3 warnings in 65.56s (0:01:05)
```
And the same test fails in isolation, so this is co-dependency on collection order, not
a flake:
```
$ uv run pytest -q tests/test_batch_endpoint.py
6 passed, 1 error in 3.96s
$ uv run pytest -q tests/test_alembic_migration.py tests/test_batch_endpoint.py
7 passed, 1 warning, 1 error in 4.22s
```

**E2.5 — models on disk but absent from the metadata registry**
```
$ for f in api/sbs_api/db/models/*.py; do b=$(basename "$f" .py); [ "$b" = "__init__" ] && continue;
    grep -q "models\.$b import" api/sbs_api/db/models/__init__.py || echo "MISSING: $b -> $(grep -h '__tablename__' "$f" | head -1)"; done
MISSING: digest_audit  ->      __tablename__ = "digest_audit"
MISSING: fi_brand_alias  ->      __tablename__ = "fi_brand_aliases"
MISSING: fi_circuit_breaker  ->      __tablename__ = "fi_circuit_breakers"
MISSING: incident_annotation  ->      __tablename__ = "incident_annotations"
MISSING: indecopi_case  ->      __tablename__ = "indecopi_cases"
MISSING: manual_finding  ->      __tablename__ = "manual_findings"
MISSING: pattern_detection  ->      __tablename__ = "pattern_detections"
MISSING: social_signal  ->      __tablename__ = "social_signals"
MISSING: validation_audit  ->      __tablename__ = "validation_audit"
```
A migration for the table does exist — it is only the ORM registry that is missing it:
```
$ grep -rln "fi_brand_aliases" api/migrations/versions/
api/migrations/versions/20260528_0005_social_and_broadcast.py
```

**E2.6 — the fixture ordering that turns E2.5 into a failure**
```
$ sed -n '169,186p' tests/conftest.py
    from sbs_api.db.base import Base
    from sbs_api.db import models  # noqa: F401  - import for metadata side effects
    ...
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
$ grep -n "FIBrandAlias" tests/conftest.py
251:        from sbs_api.db.models.fi_brand_alias import FIBrandAlias
256:                FIBrandAlias(
```
`create_all` runs at line 185; `FIBrandAlias` first registers itself on `Base.metadata`
at line 251 — after the table would have been created.

**E2.7 — the live component of `stage-g-full`, run standalone**
```
$ uv run python scripts/smoke_stage_g_live.py ; echo "exit=$?"
[18:07:31] compose services up: ['keycloak', 'postgres', 'redis', 'webhook-listener', 'worker']
[18:07:31] listener ready: ready at 1786382206.074 on port 8080
[18:07:31] using batch_id=batch_019fecdbbde07aa393d4b8fff862
[18:07:31] wrote .../data/batches/batch_019fecdbbde07aa393d4b8fff862.csv (797 bytes, sha256=3c5e0ddfe65175bb…)
[18:07:31] inserted batches row in state=pending
[18:07:31] enqueued process_batch(...) as job b5f51a58f69c4111b2455894b216d412
[18:07:32] batch complete: accepted=3, rejected=0
[18:07:33] listener PASS line present for batch batch_019fecdbbde07aa393d4b8fff862
[18:07:33] stage-g-full live assertion: PASS
exit=0
```

**E2.8 — banned patterns in the FULL-gate-exclusive path**
```
$ grep -nE "MockTransport|TestClient|ASGITransport|dependency_overrides|mock\.patch|patch\(" scripts/smoke_stage_g_live.py
(no hits)
```

**E2.9 — banned patterns in the contract suite (exempt, disclosed for completeness)**
```
tests/test_batch_endpoint.py: 1 hits
tests/test_batch_status_endpoint.py: 1 hits
tests/test_webhook_url_validation.py: 1 hits
tests/test_webhook_delivery.py: 5 hits
tests/test_fixture_conformance.py: 5 hits
```
`scripts/smoke-test-batch.sh:137-141` documents this in the gate itself.

### E3 — Agent reality

**E3.1 — Tier 1 submission through the full auth chain (BANCO_DEMO_001 = SBS-001234)**

OAuth token (issued by the **API's own** `/v1/oauth/token`, not Keycloak):
```
{
  "iss": "https://sbs-suptech-sandbox.local",
  "aud": "sbs-api",
  "iat": 1786383504,
  "exp": 1786384404,
  "sub": "SBS-001234",
  "scope": "complaints:read complaints:write",
  "cnf": { "x5t#S256": "a74455956782b63f427a62705475f7381d647aa73c6f5e24674a3623b1ab2e90" }  # pragma: allowlist secret
}
```
Signed POST (mTLS client cert `dev-ca/banco-demo-001.pem`, Bearer token, HMAC-SHA256
over the ADR 0027 canonical request):
```
complaint_id=BCO-2026-598556  institution_id=SBS-001234  timestamp=2026-08-10T17:38:25Z
request body: {"complaint":{"complaint_id":"BCO-2026-598556","institution_id":"SBS-001234","received_date":"2026-08-10","complainant_doc_type":"DNI","product_category":"TARJETA_CREDITO","channel":"APP_MOVIL","motivo_code":"COBRO_INDEBIDO","severity":"HIGH","description_text":"Me cobraron una comision de mantenimiento que nunca autorice en mi tarjeta de credito, y el banco no responde mis reclamos.","description_language":"es","complainant_age_range":"35_44","complainant_district":"150100","submission_method":"APP_MOVIL","original_reference_id":null,"resolution_status":"pendiente"}}
--- response ---
HTTP/1.1 201 Created
location: /v1/complaints/BCO-2026-598556
etag: "0d6f1e27fdc18f706360b619"  # pragma: allowlist secret
x-ratelimit-limit: 1000
x-ratelimit-remaining: 999
x-correlation-id: 82111be0-e630-4f06-9e2a-56de18c167dc
traceparent: 00-664dac26ff1a6e51d26e6eb20354e9c8-cf6139e4871c9de6-01

{"complaint_id":"BCO-2026-598556","institution_id":"SBS-001234","received_at":"2026-08-10T17:38:25.348445Z","resolution_status":"pendiente","client_submission_id":null}
```
**Correlation ID: `82111be0-e630-4f06-9e2a-56de18c167dc`.**

The API was started with `SBS_API_MTLS_MODE=direct`, `SBS_API_AUTH_STUB_ENABLED=false`,
`SBS_API_PORT=8443` **and `SBS_API_AGENTS_PIPELINE_ENABLED=true`**.

**E3.2 — LangGraph is absent, and ADR 0001 says so deliberately**
```
$ grep -rn -i "langgraph" pyproject.toml uv.lock          → (no matches)
$ grep -rn -i "langgraph" api/ scripts/ tests/            → (no code imports)

docs/adr/0001-three-layer-mcp-a2a-langgraph.md:
- **Supersedes:** The original Proposed entry at the same number
  ("MCP + A2A + LangGraph three-layer agent architecture"). ... the
  concrete MCP / A2A / LangGraph stack is rejected in favour of an
  in-house tool-calling loop ... The slug is kept verbatim so the
  ADR-index anchor for "0001" still resolves.
...
The agent runtime is a **tool-calling loop** (not LangGraph).
```

**E3.3 — no agent ran for the Tier 1 submission**

The complaint persisted:
```
  complaint_id   | institution_id |    source    | resolution_status |          received_at
-----------------+----------------+--------------+-------------------+-------------------------------
 BCO-2026-598556 | SBS-001234     | api_realtime | pendiente         | 2026-08-10 17:38:25.348445+00
```
The newest `agent_runs` rows at that moment were a month old:
```
$ psql -c "select id, agent_name, status, started_at from agent_runs order by started_at desc limit 10;"
 c0e3c328-… | synthesis                   | success | 2026-07-13 19:42:12.349377+00
 ad4e0b3c-… | investigation               | success | 2026-07-13 19:42:11.479377+00
 03fbb947-… | triage                      | success | 2026-07-13 19:42:11.019377+00
 77671ccc-… | live-ingestion-orchestrator | partial | 2026-07-13 19:42:10.953527+00
 …
```

**E3.4 — `POST /v1/complaints` has no agent call site**
```
$ grep -n "^from\|await " api/sbs_api/routes/complaints.py
… assert_ingestion_allowed, claim_idempotency_slot, session.flush, mark_complete,
   session.commit, session.execute …
(no import of, or call to, run_agent_pipeline / run_tier1_ingestion)
```

**E3.5 — `agents_pipeline_enabled` has exactly one reader**
```
$ grep -rn "agents_pipeline_enabled\|AGENTS_PIPELINE_ENABLED" --include="*.py" --include="*.sh" .
scripts/demo.sh:62:export SBS_API_AGENTS_PIPELINE_ENABLED=true
scripts/demo.sh:64:echo "demo.sh: SBS_API_AGENTS_PIPELINE_ENABLED=${SBS_API_AGENTS_PIPELINE_ENABLED}" \
api/sbs_api/config.py:318:    agents_pipeline_enabled: bool = Field(
api/sbs_api/demo_ingestion/orchestrator.py:796:    if settings.agents_pipeline_enabled:
```

**E3.6 — triage run on the audited complaint (default provider)**
```
$ env -u SBS_API_MODEL_PROVIDER uv run python <runner> BCO-2026-598556
WARNING sbs_api.agents.providers.on_prem: on_prem provider falling back to mock: vLLM unreachable: ConnectError('All connection attempts failed') (base_url=http://localhost:8001/v1, model=Qwen2.5-7B-Instruct) — demo-safe but not regulator-grade
INFO sbs_api.agents.runtime.loop: agent_iteration
INFO sbs_api.agents.runtime.loop: agent_iteration
INFO sbs_api.agents.orchestrator: agent pipeline stopping at triage: route_to=info-only complaint=BCO-2026-598556
### SBS_API_MODEL_PROVIDER env = None
### resolved provider object = OnPremProvider (name='on_prem')
### route_to = info-only
### triage = {'classification': {'label': 'other', 'confidence': 0.55, 'alternatives': [], 'model_id': 'rules-v1'}, 'priority': 'low', 'dq_summary': {'errors': 0, 'warnings': 0}, 'taxonomy_summary': {'normalized_count': 0, 'unknown_count': 0}, 'route_to': 'info-only', 'reasoning_summary': 'triage-complete'}
```

**E3.7 — the persisted `agent_runs` row: three real tool calls against live Postgres**
```
id            | 128eccb7-52ac-45a6-8290-a0c46d0e0a5c
agent_name    | triage
agent_version | triage-0.1.0
status        | success
started_at    | 2026-08-10 17:40:05.154621+00
ended_at      | 2026-08-10 17:40:05.245834+00
tool_calls    | [ { "tool_name": "query_dq_results",               "tool_version": "v1",        "status": "success", … },
              |   { "tool_name": "query_taxonomy_normalizations",  "tool_version": "v1",        "status": "success", … },
              |   { "tool_name": "classify_complaint",             "tool_version": "rules-v1",  "status": "success",
              |     "output": { "label": "other", "model_id": "rules-v1", "confidence": 0.55, "alternatives": [] } } ]
final_output  | { "priority": "low", "route_to": "info-only",
              |   "dq_summary": { "errors": 0, "warnings": 0 },
              |   "classification": { "label": "other", "model_id": "rules-v1", "confidence": 0.55 },
              |   "taxonomy_summary": { "unknown_count": 0, "normalized_count": 0 },
              |   "reasoning_summary": "triage-complete" }
```

**E3.8 — investigation + synthesis run on the triaged case**
```
WARNING sbs_api.agents.providers.on_prem: on_prem provider falling back to mock: vLLM unreachable … — demo-safe but not regulator-grade
INFO sbs_api.agents.runtime.loop: agent_iteration   (×5)
### provider: OnPremProvider on_prem
### investigation final_output: {'feature_attribution': [{'name': 'product_category', 'contribution': 0.12}, {'name': 'motivo_code', 'contribution': 0.09}, {'name': 'amount_band', 'contribution': 0.06}], 'feature_model_id': 'xgboost-replay-v1', 'anomaly': {'composite_score': 0.17, 'threshold': 0.7, 'anomaly_flag': False, …, 'model_id': 'composite-v1'}, 'similar_complaints': [{'complaint_id': 'BCO-2026-4602737', …}, {'complaint_id': 'BCO-2026-9073992', …}, {'complaint_id': 'BCO-2026-5047779', …}, {'complaint_id': 'BCO-2026-9641482', …}, {'complaint_id': 'BCO-2026-2054708', …}], 'similar_strategy': 'exact-match', 'draft_narrative': {'text': "Reclamo BCO-2026-598556: clasificación inicial '—'. Pendiente revisión analista.", 'length': 80, 'model_id': 'draft-v1'}, 'reasoning_summary': 'investigation-complete'}
### synthesis final_output: {'executive_summary': {'text': 'Reclamo BCO-2026-598556: pendiente revisión. No hay señales fuera de umbral en los canales monitoreados.', 'key_points': ['Sin señales fuera de umbral.'], 'audience': 'superintendent', 'model_id': 'summarize-v1'}, 'audit_trail_highlights': [{'action': 'agent-run-completed', 'actor_id': 'triage', …}, {'action': 'agent-run-completed', 'actor_id': 'investigation', …}], 'reasoning_summary': 'synthesis-complete'}
```
The five `similar_complaints` are real rows from the live database, so the tool executed
against live services. `feature_model_id: xgboost-replay-v1` and the `'—'` placeholder
inside the draft narrative are the P2-3 / P2-4 findings.

**E3.9 — agents DO run through the real auth chain, via the granular sandbox route**
```
### POST /v1/sandbox/complaints/granular (mTLS + Bearer + HMAC)
HTTP/1.1 201 Created
location: /v1/complaints/BCO-2026-4957653
x-correlation-id: 10ff5b48-42a7-4f46-8a73-6cc64086c83f
traceparent: 00-9fd97eb8d2e3904bfa4912165d76d86b-4fe61b0f2b2627ca-01

"timeline":[
 {"event":"received"},
 {"event":"institution_authenticated_simulated","detail":"shared-secret + role check"},
 {"event":"schema_validated","detail":"Anexo 1-A-like fields parsed"},
 {"event":"taxonomy_normalized","detail":"mapped=3 unknown=0 dictionary=taxonomy-v1"},
 {"event":"pii_redacted","detail":"entities=0 policy=pii-redaction-demo-v1"},
 {"event":"canonical_complaint_persisted","detail":"complaint_id=BCO-2026-4957653 source=api_realtime"},
 {"event":"data_quality_checks_completed","detail":"errors=0 warnings=1 policy=dq-demo-v1"},
 {"event":"annex_1a_checks_completed","detail":"errors=4 warnings=3 policy=annex-1a-v1"},
 {"event":"finding_triage_event_emitted","detail":"audit chain x13 (6 chain + 7 dq-rule-violated + 0 taxonomy-unknown-term)"},
 {"event":"agent_pipeline_completed","detail":"route=info-only triage=ok investigation=skip synthesis=skip"}]
```
Note the absence of any DIValeVale stage. Annex 1-A rules fired with campo numbering,
e.g. `DQ-A1A-007 … "Tipo de documento (Anexo 1-A campo 2) es obligatorio."`

**E3.10 — that route is not in the canonical contract**
```
$ grep -n "sandbox" api/openapi/sbs-api-v1.yaml | head
33:    The `complaint_id` is unique **globally within the SBS sandbox**, not
35:    the same `complaint_id`. The May 25 sandbox enforces this by assigning
59:  - url: https://api-sandbox.sbs.gob.pe/v1
897:            sandbox accepts the canonical 6-digit form; district digits
```
Prose mentions only — no `/sandbox/complaints/granular` path item.

**E3.11 — provider evidence, from the API process itself**
```
$ grep -n "falling back to mock" <api-8443 stderr>
2285:on_prem provider falling back to mock: vLLM unreachable: ConnectError('All connection attempts failed') (base_url=http://localhost:8001/v1, model=Qwen2.5-7B-Instruct) — demo-safe but not regulator-grade

$ psql -c "select agent_name, agent_version, status, started_at, jsonb_array_length(tool_calls) as n_tools from agent_runs where complaint_id='BCO-2026-4957653' order by started_at;"
         agent_name          |           agent_version           | status  |          started_at           | n_tools
-----------------------------+-----------------------------------+---------+-------------------------------+---------
 live-ingestion-orchestrator | live-ingestion-orchestrator-0.1.0 | partial | 2026-08-10 18:28:09.179387+00 |       1
 triage                      | triage-0.1.0                      | success | 2026-08-10 18:28:09.197001+00 |       3
```
Every model call in this audit was served by **MockProvider**, reached through
`OnPremProvider`'s fallback. `ReplayProvider` was never selected.

**E3.12 — DIValeVale is not in any runtime path**
```
$ grep -rn "validate_tier1_record" --include="*.py" .
tests/agents/divalevale/test_llm_fallback_invalid_output.py:15,65
tests/agents/divalevale/test_routing_tier1.py:13,46,72,106,125,151,205
api/sbs_api/ingestion/pipeline.py:22,58
api/sbs_api/agents/divalevale/agent.py:82,214

$ grep -rn "run_tier1_ingestion" --include="*.py" .
tests/integration/test_divalevale_full_chain.py:19,49,75
api/sbs_api/ingestion/pipeline.py:8,33          ← definition + docstring only

$ grep -n -i "divalevale\|validate_tier1" api/sbs_api/demo_ingestion/orchestrator.py
(no matches)

$ psql -c "select count(*) from validation_audit;"
 0
```
So: `validate_tier1_record` ← `run_tier1_ingestion` ← **tests only**.

**E3.13 — the registry's other three agents have no implementation**
```
$ for a in issue-resurface peer-risk-radar sector-broadcast insight-chatbot divalevale; do
    echo "-- $a --"; grep -rln "$a" api/sbs_api --include="*.py"; done
-- issue-resurface --
api/sbs_api/agents/registry.py
-- peer-risk-radar --
api/sbs_api/agents/registry.py
api/sbs_api/agents/status.py
-- sector-broadcast --
api/sbs_api/agents/registry.py
api/sbs_api/agents/status.py
-- insight-chatbot --
api/sbs_api/agents/registry.py
-- divalevale --
api/sbs_api/ingestion/pipeline.py
api/sbs_api/agents/registry.py
api/sbs_api/agents/divalevale/pass2_extraction.py
api/sbs_api/agents/divalevale/agent.py

$ psql -c "select agent_name, count(*), max(started_at) from agent_runs group by 1 order by 1;"
 cross-source-correlator     |     1 | 2026-07-13 14:53:14.880148+00
 investigation               |    33 | 2026-08-10 17:41:05.289899+00
 live-ingestion-orchestrator |    31 | 2026-07-13 19:42:10.953527+00
 synthesis                   |    33 | 2026-08-10 17:41:05.378038+00
 triage                      |    92 | 2026-08-10 17:40:05.154621+00
```
Never a single run for `divalevale`, `issue-resurface`, `peer-risk-radar`,
`sector-broadcast` or `insight-chatbot`.

**E3.14 — cross-source-correlator is replay-driven and skipped without a fixture**
```
api/sbs_api/agents/orchestrator.py:
            try:
                cross_source_out = await run_cross_source_correlator(...)
            except ReplayFixtureMissing:
                # Non-demo complaints do not have a fixture yet — skip
                # the scaffolded agent quietly rather than raising.
                cross_source_out = None
```

**E3.15 — provider identity is not persisted**
```
$ psql -c "\d agent_runs"
 id | complaint_id | agent_name | agent_version | started_at | ended_at | status | tool_calls | final_output | error
```
No `model_provider` (or equivalent) column.

**E3.16 — the arq worker does not run agents**
```
scripts/run_agent_pipeline_on_new.py:4-8
Batch ingestion is processed by the arq worker container, whose environment
does not enable the agent pipeline (it defaults off so the Prompt-11
regression suite stays green). This host-side pass closes that gap for the
demo: after a batch lands, it finds every complaint with zero ``agent_runs``
rows and runs triage -> investigation -> synthesis against them …
```

**E3.17 — `classify_complaint` key space vs the API's enums**
```
api/sbs_api/agents/tools/classify.py
"""classify_complaint — deterministic complaint classifier.
In production this would call BETO via vLLM; for the May 27 demo
the tool returns deterministic mappings keyed by (product, motive)."""
RULES_TABLE = {
    ("credit-card", "undisclosed-fee"): ("undisclosed-fees-credit", 0.87),
    ("credit-card", "comisiones"):      ("undisclosed-fees-credit", 0.82),
    …
}
DEFAULT_LABEL = "other"; DEFAULT_CONFIDENCE = 0.55
    if complaint_id == DEMO_COMPLAINT_ID:      # BCO-2026-000001
        return {"label": "undisclosed-fees-credit", "confidence": 0.87, …,
                "model_id": "beto-replay-v1"}
```
The API's accepted values are `TARJETA_CREDITO` / `COBRO_INDEBIDO` (see the enum in the
batch rejection at E3.20), which never key into `RULES_TABLE`.

**E3.18 — `rank_features` returns a constant**
```
api/sbs_api/agents/tools/rank_features.py
DEMO_FEATURES = [ … 5 items, demo complaint only … ]
DEFAULT_FEATURES = [
    {"name": "product_category", "contribution": 0.12},
    {"name": "motivo_code",      "contribution": 0.09},
    {"name": "amount_band",      "contribution": 0.06},
]
    version = "xgboost-replay-v1"
```

**E3.19 — Tier 2 batch through the full auth chain (COOPAC_DEMO_002 = SBS-005678)**
```
### STEP 1 — OAuth token (scope batch:upload status:read)  → len 418
### STEP 2 — POST /v1/batches (multipart, mTLS + Bearer + HMAC)
rows: COP-2026-737757 , COP-2026-737758
manifest: {"reporting_period_start":"2026-08-01","reporting_period_end":"2026-08-10","row_count_submitted":2,"checksum_sha256":"688b46258b522c301c1c4840f220b56ee05b5274442545c6f58f16f6c96d0129","schema_version":"v0.1.0"}  # pragma: allowlist secret
HTTP/1.1 202 Accepted
location: /v1/batches/batch_019fecc4a2227df3b5af235a7482
x-correlation-id: c2e99340-e740-4048-b7da-2be1a1e3a3fd
traceparent: 00-64f934d5428333ee8ed3648de3f6c321-5b756287fbee6361-01

{"batch_id":"batch_019fecc4a2227df3b5af235a7482","status":"pending"}
```
The live arq worker processed it:
```
batch_019fecc4a2227df3b5af235a7482 | complete | accepted=1 | rejected=1
```

**E3.20 — the rejected row: real validation, working correctly**
```
batch_id        | batch_019fecc4a2227df3b5af235a7482
row_index       | 1
field           | product_category
rule            | enum
message         | Input should be 'DEPOSITOS', 'CREDITOS', 'TARJETA_CREDITO', 'TARJETA_DEBITO', 'SEGUROS', 'AFP_PENSIONES', 'COOPAC' or 'OTRO'
raw_row_excerpt | {"complaint_id": "COP-2026-737758", …, "product_category": "CUENTA_AHORROS", …}
```
This is an error in the auditor's test CSV (`CUENTA_AHORROS` is not a valid enum), not a
defect. It is retained as evidence that batch-row validation genuinely runs.

**E3.21 — Tier 1 and Tier 2 land as the same canonical record**
```
$ psql -c "select complaint_id, institution_id, source, product_category, motivo_code, severity, resolution_status from complaints where complaint_id in ('COP-2026-737757','COP-2026-737758');"
  complaint_id   | institution_id | source | product_category |  motivo_code   | severity | resolution_status
-----------------+----------------+--------+------------------+----------------+----------+-------------------
 COP-2026-737757 | SBS-005678     | batch  | TARJETA_CREDITO  | COBRO_INDEBIDO | HIGH     | pendiente
```
Both tiers write the same `public.complaints` table with the same column set,
distinguished only by `source` (`api_realtime` vs `batch`). Both appear in the same
cockpit view — see E4.6.

### E4 — UI wiring

**E4.1 — all 20 routes render 200 with a real session**
```
/cockpit                       http=200 bytes=93866    backend_calls=2
/cockpit/aggregates            http=200 bytes=67442    backend_calls=0
/queue                         http=200 bytes=33440    backend_calls=0
/findings                      http=200 bytes=58473    backend_calls=1
/approvals                     http=200 bytes=39278    backend_calls=1
/audit                         http=200 bytes=252763   backend_calls=1
/analytics                     http=200 bytes=85004    backend_calls=0
/ingestion                     http=200 bytes=250403   backend_calls=0
/processing                    http=200 bytes=34245    backend_calls=0
/assistant                     http=200 bytes=53868    backend_calls=0
/admin                         http=200 bytes=39601    backend_calls=0
/docs                          http=200 bytes=38423    backend_calls=0
/sandbox                       http=200 bytes=49988    backend_calls=0
/rr1                           http=200 bytes=188945   backend_calls=0
/demo-journey                  http=200 bytes=35498    backend_calls=0
/developers                    http=200 bytes=60957    backend_calls=0
/developers/credentials        http=200 bytes=43390    backend_calls=0
/fi/banco-demo-001/inbox       http=200 bytes=232432   backend_calls=0
/fi/banco-demo-001/send        http=200 bytes=21791    backend_calls=0
/fi/coopac-demo-002/send       http=200 bytes=21811    backend_calls=0
```
`backend_calls` counts `http.route` log lines emitted by the FastAPI process during the
server render; a `0` means the page fetches client-side, not that it is static.

**E4.2 — Keycloak-backed demo session works (and the 0.0.0.0 redirect)**
```
$ curl -s -i http://localhost:3000/app/api/auth/demo-login | head -6
HTTP/1.1 307 Temporary Redirect
location: http://0.0.0.0:3000/app/cockpit
set-cookie: sbs-session=bHD2…<redacted:session-cookie>; Path=/; HttpOnly; SameSite=lax
set-cookie: sbs-csrf=jlWD…<redacted:csrf-token>; Path=/; SameSite=lax
```
`demo-login` acquires persona tokens from Keycloak via ROPC, so Keycloak **is** on the
supervisor-session path (ADR 0040) — while the institution API path issues its own JWTs.

**E4.3 — BFF routes, and which reach the backend**
```
/api/aggregates/trend            http=200 backend_calls=1 body={"generated_at":"2026-08-10T18:23:35.231635+00:00","by_motivo":[{"motivo_code":"COBRO_INDE…
/api/aggregates/patterns         http=200 backend_calls=1 body={"scope":"entity","generated_at":"…","total_in_scope":96,…
/api/aggregates/sources          http=200 backend_calls=1 body={"generated_at":"…","social_by_indicator":[],"social_instit…
/api/aggregates/social           http=200 backend_calls=0 body={"available":false}
/api/aggregates/feed             http=200 backend_calls=1 body={"items":[{"complaint_id":"BCO-2026-0003852511","institution_id":"SBS-001234",…
/api/journey/stats               http=200 backend_calls=0 body={"hourly_24h":[{"hour":"17:00","count":2},{"hour":"18:00","count":3}],…
/api/journey/recent              http=200 backend_calls=0 body={"items":[{"complaint_id":"BCO-2026-0003852511",…
/api/journey/insights            http=200 backend_calls=0 body={"kpis":{"complaints_24h":5,"complaints_7d":5,"active_institutions":2,"anomalies_active":3…
/api/admin/audit                 http=200 backend_calls=1 body={"items":[{"id":495,"created_at":"2026-08-10T18:23:34+00:00",…
/api/explain/foo                 http=401 backend_calls=0 body={"error":"no_active_persona"}
```
`/api/journey/*` show `backend_calls=0` yet return live data (`complaints_24h: 5` matches
this audit's submissions) because they query Postgres directly — see E4.4.

**E4.4 — journey routes shell out to a hard-coded venv path**
```
app/src/app/api/journey/stats/route.ts
// Shells out to scripts/cockpit_stats.py (avoids bundling Postgres
// drivers in the Next.js runtime and reuses the venv's psycopg).
const REPO_ROOT = path.resolve(process.cwd(), '..');
const VENV_PY   = path.join(REPO_ROOT, '.venv', 'bin', 'python');
const SCRIPT    = path.join(REPO_ROOT, 'scripts', 'cockpit_stats.py');
```

**E4.5 — static sample data is honestly badged**
```
app/src/components/persona/AggregateTables.tsx
30: import { DSC_SAMPLE, FRAUD_LABEL_ES, INDECOPI_SAMPLE, SOCIAL_SAMPLE } from '@/lib/source-samples';
43: // SBS DSC = clearly-labelled sample (no real endpoint).
218:// Sample source data lives in @/lib/source-samples (shared, badged "datos de
232:  {bi(locale, 'datos de muestra', 'sample data')}
```

**E4.6 — the decisive check: audited records appear in the rendered pages**
```
$ for f in pg_*.html; do grep -c "BCO-2026-598556" / "COP-2026-737757" …
pg_audit:    tier1_hits=7  tier2_hits=0
pg_cockpit:  tier1_hits=2  tier2_hits=1
pg_findings: tier1_hits=1  tier2_hits=1
```
`/app/cockpit` renders **both** the Tier 1 (`BCO-2026-598556`) and the Tier 2
(`COP-2026-737757`) record submitted during this audit — satisfying §3(d).

**E4.7 — server-side data fetches**
```
$ grep -rn "from '@/lib/api'" app/src/app --include="*.tsx"
app/src/app/(supervisor)/cockpit/page.tsx:14:      import { internalGet } from '@/lib/api';
app/src/app/(supervisor)/audit/page.tsx:14
app/src/app/(supervisor)/findings/page.tsx:13
app/src/app/(supervisor)/findings/[id]/page.tsx:20
app/src/app/(supervisor)/approvals/page.tsx:14
app/src/app/(supervisor)/approvals/[id]/page.tsx:17
```

**E4.8 — every client fetch target is a `/app/api/*` BFF route**
```
   4 /app/api/aggregates/trend            1 /app/api/persona/switch
   3 /app/api/journey/submit              1 /app/api/journey/stats
   2 /app/api/aggregates/patterns?…       1 /app/api/journey/recent?limit=40
   2 /app/api/aggregates/feed             1 /app/api/journey/recent?limit=20
   1 /app/api/sandbox/tier2/submit        1 /app/api/journey/insights
   1 /app/api/sandbox/tier2/status?…      1 /app/api/journey/findings?…
   1 /app/api/sandbox/tier1/send          1 /app/api/journey/audit?…
   1 /app/api/sandbox/tier1/pool          1 /app/api/ingest
   1 /app/api/aggregates/sources          1 /app/api/demo/assistant
   1 /app/api/aggregates/social           1 /app/api/complaints/${…}
   1 /app/api/aggregates/chat             1 /app/api/approvals/${…}/${…}
   1 /app/api/admin/audit?page_size=20
```

**E4.9 — static data imports**
```
-- golden-complaint --   app/src/app/fi/banco-demo-001/inbox/page.tsx
                         app/src/app/(supervisor)/demo-journey/page.tsx
-- rr1-2025 --           app/src/app/(supervisor)/rr1/page.tsx
-- journey-emails --     app/src/app/fi/banco-demo-001/inbox/page.tsx
                         app/src/app/fi/banco-demo-001/submit/[rowIndex]/page.tsx
                         app/src/app/fi/banco-demo-001/triage/[rowIndex]/page.tsx
                         app/src/app/(supervisor)/ingestion/page.tsx
-- source-samples --     app/src/components/persona/RedFlags.tsx
                         app/src/components/persona/AggregateTables.tsx
```

### E5 — Schema conformance

**E5.1 — "27 fields" heading over a 28-row table**
```
$ sed -n '700,732p' app/src/components/docs/DocsTabs.tsx | grep -c "{ key: '"
28

app/src/components/docs/DocsTabs.tsx (heading, immediately after the array):
  {es ? 'Anexo 1-A · Res. SBS 4036-2022 · 27 campos' : 'Annex 1-A · Res. SBS 4036-2022 · 27 fields'}
```
The 28 rows, in order: `COD_REC, TID_CLI, NRO_CLI, NCL_CLI, COD_CLI, FEC_ING, CNL_ING,
CNL_OPE, FEC_AMP, CNL_AMP, FEC_RES, CNL_PAC, UBI_REC, PRD_SBS, MOT_SBS, SUB_SBS, DET_REC,
TIP_RES, DET_RES, PRD_EMP, EST_REC, COD_PRV, BAN_SEG, PRD_SBS_SEG, MOT_SBS_SEG,
SUB_SBS_SEG, MNT_PEN_REC, EMPRESA`.

**E5.2 — the bancaseguros block: 1 trigger + 3 conditional**
```
tests/test_annex_1a_rules.py:67-68
    # Field 24 + bancaseguros block (trigger=no → 25/26/27 optional)
    "bancaseguros": "no",
tests/test_annex_1a_rules.py:380-383
        "bancaseguros": "si",
        "producto_bancaseguros": "103",
        "motivo_bancaseguros": "44",
        "submotivo_bancaseguros": "50",
```

**E5.3 — no `bancaseguros_nombre` drift**
```
$ grep -rn "bancaseguros_nombre" .
(none — clean)
```

**E5.4 — DQ rules put the conditionals at campos 25/26/27**
```
$ grep -o "Anexo 1-A campo [0-9]*" api/sbs_api/data_quality/annex_1a_rules.py | sort -u -n -k4
Anexo 1-A campo 2 / 3 / 5 / 6 / 7 / 11 / 16 / 18 / 22 / 25 / 26 / 27
api/sbs_api/data_quality/annex_1a_rules.py:499
    message="bancaseguros=si exige producto_bancaseguros (Anexo 1-A campo 25)."
```

**E5.5 — the 28-column layout in the sample ingestor**
```
scripts/ingest_sample_dataset.py:80-109
_COL_INDEX = { "COD_REC": 0, …, "BAN_SEG": 22, "PRD_SBS_SEG": 23, "MOT_SBS_SEG": 24,
               "SUB_SBS_SEG": 25, "MNT_PEN_REC": 26, "EMPRESA": 27 }
```

**E5.6 — the wire format is a 15-field subset (ADR 0026), not 27**
```
$ head -1 data/synthetic-corpus-golden/SBS-005678/SBS-005678.csv
complaint_id,institution_id,received_date,complainant_doc_type,product_category,channel,motivo_code,severity,description_text,description_language,complainant_age_range,complainant_district,submission_method,original_reference_id,resolution_status

docs/adr/README.md
| 0026 | anexo-1a-curated-subset | Accepted | … | 15-field subset of Anexo 1-A for the May 25 sandbox, reconciled against Resolución SBS N° 04036-2022 … |
```

### E6 — Handover readiness

**E6.1 — README step 1 runs clean**
```
$ bash scripts/dev-up.sh ; echo "exit=$?"
==> alembic upgrade head
==> seeding demo institutions
    institutions: SBS-001234 (BANCO_DEMO_001), SBS-005678 (COOPAC_DEMO_002)
==> seeding institution_certificates from dev-ca/seed-certificates.sql
    certificate thumbprints loaded (see dev-ca/thumbprints.txt)
==> seeding oauth_clients (argon2id hashes)
    oauth_clients: banco-demo-001 (SBS-001234), coopac-demo-002 (SBS-005678)
==> ready
DSN: postgresql+asyncpg://sbs:sbs@localhost:5432/sbs_dev  # pragma: allowlist secret
exit=0
```
Its own header confirms the scope: `1. docker compose up -d postgres redis` — Keycloak,
the worker, the webhook-listener and the UI are not started.

**E6.2 — the README never explains how to run the cockpit**
```
$ grep -n -i "npm\|next dev\|cockpit" README.md
3:… and a supervisor cockpit.
7:![Supervisor cockpit](docs/assets/cockpit.png)
11:Prerequisites: … Node.js 20+ (for the web app under `app/`) …
```
No command, no `app/.env.local` step, no Keycloak step.

**E6.3 — the documented cockpit URL is wrong**
```
docs/demo/institution-api-workflow.md:162
cd app && npm install && npm run dev    # cockpit at http://localhost:3000/supervisor

$ curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/supervisor   → 404
$ curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/app/cockpit  → 307 (→ session flow)
```

**E6.4 — env examples**
```
$ grep -c "INTERNAL_API_SECRET" .env.example
0
$ grep -n "SBS_INTERNAL_API_SECRET" app/.env.example
SBS_INTERNAL_API_SECRET=replace-me-with-openssl-rand-hex-32
# Set the SAME value in the FastAPI process's SBS_API_INTERNAL_API_SECRET env var.
```

**E6.5 — `app/README.md` is stale**
```
Next.js 14 (App Router) application served at `/app/`. Five screens:
cockpit, risk queue, findings, approvals, audit.
…
│   ├── cockpit/page.tsx          # /app/cockpit      ← no (supervisor) route group
```
Actual route count: 28 `page.tsx` files, ~20 reachable supervisor/FI routes.

**E6.6 — ADR inventory is complete and internally consistent**
```
$ ls docs/adr/ | wc -l          → 31   (30 ADRs + README.md index)
$ grep -h "^- \*\*Status:\*\*" docs/adr/*.md | sort | uniq -c
  29 - **Status:** Accepted
   1 - **Status:** Proposed
$ <every ADR listed in docs/adr/README.md that should have a file>  → 0 missing
```
Numbers 0002–0015 and 0024 have no file because the index marks them
`Proposed (queued, not yet written)` — by design, not drift.

**E6.7 — `scripts/demo.sh` bypasses the HTTP API**
```
scripts/demo_replay.py:8-11
2. Computes its SHA-256, inserts a batch row in state=pending into
   the live Postgres, places the CSV on disk under ``data/batches/``.
3. Enqueues ``process_batch`` onto the live arq Redis pool.
```

### E7 — Read-only compliance

**E7.1 — tree unchanged; regenerated golden corpus is byte-identical**
```
before:  $ git status --porcelain   → (empty)
         $ find data/synthetic-corpus-golden -type f | sort | xargs shasum -a 256 | shasum -a 256
         1b2345643469a05993990272826624eddcbd3f63ead4bb19b18f5e0791a0dc81  -  # pragma: allowlist secret

after (post stage-e / stage-g runs, which regenerate the golden corpus):
         $ git status --porcelain   → (empty)
         $ find data/synthetic-corpus-golden -type f | sort | xargs shasum -a 256 | shasum -a 256
         1b2345643469a05993990272826624eddcbd3f63ead4bb19b18f5e0791a0dc81  -  # pragma: allowlist secret

final:   $ git status --porcelain   → (empty)
```
No tracked file was modified, created or deleted. Nothing was committed, branched or
pushed. `docker compose down -v` was not run and no destructive DB operation was
performed. Rows **added** by the audit (permitted — the brief requires submitting
complaints): complaints `BCO-2026-598556`, `COP-2026-737757`, `BCO-2026-4957653`, one
`batches` row, one `batch_row_rejections` row, and the `agent_runs` rows they produced.
`scripts/smoke-test-auth.sh` also created one complaint and temporarily set
`institutions.rate_limit_per_minute = 3` for SBS-001234, restoring it to `NULL` at the
end of its own run.

The only file created by this audit is this report.
