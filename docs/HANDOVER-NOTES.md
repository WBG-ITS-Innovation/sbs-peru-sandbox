# Handover notes

Things a new maintainer will otherwise rediscover the hard way. None of these
is a bug report — each is either a deliberate posture, a known limitation, or a
piece of operational sharp edge. Bugs live in the issue tracker; the audit trail
that produced this list is under [docs/audit/](audit/).

Start with the README for setup, including the two API processes the cockpit
needs. This file is about what to expect once it is running.

---

## Agents and model providers

**The demo posture is `replay`, and `on_prem` has still never been observed
against a real vLLM.** `SBS_API_MODEL_PROVIDER` defaults to `on_prem`, which as
of `part-12/cloud-provider-azure` raises `ProviderUnavailableError` when no vLLM
answers — the situation on every machine used in this engagement. It used to
fall back to `MockProvider` instead, which is why earlier notes and audit
reports describe a `mock` posture: the fallback is gone, because canned tool
calls reaching `agent_runs` are indistinguishable from analysis. `scripts/demo.sh`
now pins `replay`, which logs a WARNING on every request saying the response is
a replayed fixture. The first person with a vLLM endpoint should still expect
integration problems that no test on this branch could have caught.

**`cloud` (Azure OpenAI) has been exercised live** — one canary tool-call and
the full pipeline — but only against synthetic data, and only behind
`SBS_API_CLOUD_LEGAL_APPROVED=true`. On the WBG network it also needs
`SBS_API_CLOUD_CA_BUNDLE`; see `.env.example` and ADR 0015.

`agent_runs.model_provider` records which provider *actually served* each run,
not which one was configured. It discriminates in practice: with `replay`
configured, a single complaint gets `replay` rows from the loop-driven agents
and from the correlator; with `cloud` configured, the loop-driven agents record
`cloud`. Rows written before this branch may record `mock` from the old
fallback.

**`agent_runs.model_provider = NULL` means exactly one thing as of v0.2.0: the
row predates migration `20260810_0001`.** That migration added the column
nullable with no backfill, deliberately — inventing a provider for historical
rows would put a guess into an audit table. Around 200 rows in a long-lived dev
database are in this state, and **the number cannot grow.** So
`model_provider IS NOT NULL` is a safe provenance filter.

It was not safe before v0.2.0, and this is worth knowing if you query a database
that predates it. NULL used to carry a second meaning — "this run made no model
call" — which the live-ingestion orchestrator's own row hit on every
`/v1/sandbox/complaints/granular` submission, the surface the cockpit's
`/app/ingestion` loop and `scripts/sandbox_send.py` drive. On such a database
the prescribed filter silently drops current successful analysis along with the
history.

**Fixed as of this release.** A run that calls no model now records the explicit
sentinel `model_provider = 'none'` (`agents.persistence.NO_MODEL_CALL`), which is
both true and queryable, rather than a provider name it never used. No
`status='success'` row is written with a NULL provider;
`tests/integration/test_live_ingestion_endpoint.py` pins it. The remaining NULL
writers are the four agents' failed-loop paths, where the loop raised before any
response arrived and the provenance is genuinely unknown — those rows carry
`status='failed'`.

Distinguish the two when reading old data:

| `model_provider` | Meaning |
|---|---|
| `on_prem` / `replay` / `cloud` / `mock` | A model served the run; this is who actually served it |
| `none` | No model call by design — the deterministic anonymizer + DQ row |
| `NULL` | Row predates migration `20260810_0001` (or, pre-v0.2.0, made no model call) |

Found by the independent check in
[docs/audit/2026-08-17-v02-check.md](audit/2026-08-17-v02-check.md) (F3).

**The cross-source-correlator returns a degenerate result on any complaint that
is not the golden one.** It is replay-driven, and `ReplayProvider` falls back to
a generic `_default.json` when no complaint-specific fixture exists. That
default is intentionally empty:

| Complaint | Fixture | `correlation_strength` | `anomaly_flag` | signals |
|---|---|---|---|---|
| `BCO-2026-000001` | `cross-source-correlator/BCO-2026-000001.json` | 0.74 | `true` | 5 |
| anything else | `cross-source-correlator/_default.json` | 0.0 | `false` | 0 |

The run still records `status=success` with a non-null `model_provider`, so
nothing looks broken — the panel is just empty. **A demo that needs a populated
cross-source panel or the anomaly card must use `BCO-2026-000001`**, which
`scripts/dev-seed.sql` seeds for exactly this reason. Adding a fixture under
`api/sbs_api/agents/fixtures/replay/cross-source-correlator/<complaint_id>.json`
is how you get a second such complaint.

**Do not read the `except ReplayFixtureMissing` branch in
`agents/orchestrator.py` as live behaviour.** All four replay-capable agents ship
a `_default.json`, so that branch is unreachable for them; the correlator does
not silently skip. See the errata below.

## Operating the stack

**The worker container mounts the repo read-only (`.:/app:ro`) and does not pick
up code changes.** After editing anything under `api/`, recreate it or the
container keeps running the old code:

```bash
SBS_API_AGENTS_PIPELINE_ENABLED=true SBS_API_MODEL_PROVIDER=replay \
  docker compose up -d --force-recreate worker
```

**Both variables are required.** `docker-compose.yaml` reads
`SBS_API_MODEL_PROVIDER` from the invoking shell and defaults it to `on_prem`,
so recreating the worker with only the pipeline flag gives you a worker that
boots cleanly, accepts batches, and then fails **every** agent dispatch with
`ProviderUnavailableError` because no vLLM answers. Unlike the API, the worker
has no boot healthcheck to catch this: the failure appears once per complaint
in the worker log as `agents.dispatch.failed`, and `agent_runs` stays empty.
`stage-h-full`'s Tier-2 half is what catches it — `no triage agent_run for
<id> within 60s`.

`stage-h-full` has caught this staleness more than once, which is the argument
for running that gate after agent-layer changes rather than trusting the
in-process half.

**The worker's agent pipeline is off by default.** `docker compose up -d worker`
leaves `SBS_API_AGENTS_PIPELINE_ENABLED=false` so the Prompt-11 regression suite
stays green. Tier-2 ingestion still works; it just writes no `agent_runs`. Opt in
per the line above.

**`scripts/run-api.sh` no longer defaults to auto-reload.** Opt in with
`SBS_API_RELOAD=true` while developing. The reloader watches the whole repo root,
so any test or build that writes a `.py` file restarts the API — which used to
mask per-process state bugs and make gate results unreproducible.

**`scripts/demo.sh` does not go through the HTTP API.** `scripts/demo_replay.py`
inserts the `batches` row with asyncpg and enqueues `process_batch` on arq Redis
directly. It exercises the worker, the batch pipeline, and the signed outbound
webhook — but **not** mTLS, OAuth, HMAC, idempotency, or rate limiting. For the
signed-request path use `scripts/smoke-test-auth.sh`, `stage-h-full`, or a curl
walk from [docs/demo/institution-api-workflow.md](demo/institution-api-workflow.md).
Its inline comment about the worker never running agents is stale in the same
way `run_agent_pipeline_on_new.py`'s docstring was: both tiers run the chain
themselves now when the flag is on.

**`/app/api/auth/demo-login` redirects to `http://0.0.0.0:3000/app/cockpit`.**
Harmless in a browser, which follows it to localhost, but a scripted client that
follows redirects blindly will try to connect to `0.0.0.0`. Request
`/app/cockpit` directly with the `sbs-session` cookie the login response sets.

## Database and migrations

**`alembic revision --autogenerate` can no longer drop a table, but its output
still needs reading before use.** Four indexes are created by migrations and
never declared on their models, so `Base.metadata` has no claim on them and
autogenerate reports each as removed:

```
ix_complaints_flag_unknown_taxonomy
ix_institution_certificates_cn
ix_institution_certificates_institution_id
ix_oauth_clients_institution_id
```

A generated migration will contain four spurious `op.drop_index` lines. Delete
them by hand. `tests/test_alembic_migration.py::test_autogenerate_finds_no_table_level_drift`
guards the table-level case — the data-loss one — and deliberately excludes index
entries; closing the index gap means either declaring `Index(...)` on four models
or renaming indexes across shipped migrations.

## Known-incomplete by design

**DIValeVale records but does not gate.** It runs ahead of Triage on both
ingestion tiers and writes one `validation_audit` row per complaint, but its
verdict does not stop anything, and enrichment side effects are suppressed
(`record_only=True`). On the canonical Tier-1 surface the verdict is currently
`INVALID` / `REJECTED` for every real record. Two things must land before it can
become a gate:

1. **An authoritative `institution_id → institution_code` mapping.** Pass 1
   requires `institution_code` matching `^[A-Z]{3}_[A-Z]+_\d{3}$`. Every surface
   issues `SBS-001234`-style ids, and no mapping exists in the code or the
   database.
2. **An ADR 0026 decision on `amount_claimed` and `currency`.** ADR 0026 fixes
   Tier 1 at a 15-field Anexo 1-A subset carrying neither, while Pass 1 requires
   an amount for the `COBRO_INDEBIDO` family. Enforcing today would either stop
   Triage on every real Tier-1 record or fire a spurious enrichment webhook at
   the institution for each one.

The adapter deliberately omits absent fields rather than defaulting them, so the
gap shows in `pass1_failed_rules` instead of becoming a fabricated value in a
regulator-facing table. A test pins that.

**Other scaffolds, so nobody mistakes them for finished work:** `rank_features`
returns a constant `DEFAULT_FEATURES` list under `xgboost-replay-v1`; the
investigation draft narrative renders `clasificación inicial '—'` when a
classification is absent; `reclamito`, `lupaman` and `insight-chatbot` are
registry entries with no runtime.

---

## Errata against the audit trail

The reports under [docs/audit/](audit/) are dated and closed — they are never
edited, so corrections live here.
[docs/audit/2026-08-11-verification.md](audit/2026-08-11-verification.md) is the
authoritative state of the three; where it disagrees with an earlier report, it
wins.

- **The audit's cross-source-correlator fixture claims are wrong** (verification
  §6.1 / D3). `2026-08-10-handover-audit.md` states that the correlator is
  "skipped silently when no fixture exists", that "replay fixtures exist only for
  the demo complaint `BCO-2026-000001`", and that "no replay fixture matched the
  audited complaints, so it was skipped at runtime". A `_default.json` has existed
  for all four replay-capable agents since the original agent-layer commit, so no
  fixture is ever missing for them and the correlator is never skipped. The
  correlator did not run during that audit because the chain had no call site on
  the ingestion path — the audit's own P0-3 — not for want of a fixture. What is
  true, and what no report stated, is that the fallback output is empty; see the
  table above.

- **`2026-08-10-p0-fix-report.md` §F6 overstates its scope** (verification §3 /
  D1). It reports README steps 2–3 passing "run literally", but its transcript
  exports `SBS_API_PORT=8443`, which README step 2 did not contain. The `.env`
  precedence bug that section fixed is genuinely fixed; the README's
  three-command path was still broken, and was fixed separately later.

- **`2026-08-10-p0-fix-report.md` §F8 overstates its result** (verification §6.1
  / D4). "The chain now runs to depth on a real Tier-1 complaint" is true about
  depth — four agents run — and misleading about substance, because the
  correlator stage contributes nothing on a non-golden complaint.

- **`2026-08-11-f10-report.md` §Newly discovered was right, and is now fixed.**
  Its `MockProvider` cursor diagnosis reproduced exactly. Its expectation that
  the fix would break tests asserting the old semantics did not: every existing
  test uses one complaint per provider instance, so the change was transparent to
  all of them.
