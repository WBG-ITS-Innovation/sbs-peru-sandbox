# Handover notes

Things a new maintainer will otherwise rediscover the hard way. None of these
is a bug report — each is either a deliberate posture, a known limitation, or a
piece of operational sharp edge. Bugs live in the issue tracker; the audit trail
that produced this list is under [docs/audit/](audit/).

Start with the README for setup, including the two API processes the cockpit
needs. This file is about what to expect once it is running.

---

## Agents and model providers

**The provider posture is `mock` or `replay`, and `on_prem` has never been
observed against a real vLLM.** `SBS_API_MODEL_PROVIDER` defaults to `on_prem`,
which falls back to `MockProvider` whenever no vLLM answers — the situation on
every machine used in this engagement. So the agent layer works and is
deterministic, but nothing here has been exercised against a live model server.
The first person with a vLLM endpoint should expect to find integration
problems that no test on this branch could have caught.

`agent_runs.model_provider` records which provider *actually served* each run,
not which one was configured, so the fallback shows up honestly as `mock`. It
discriminates in practice: a single complaint routinely has `mock` rows from the
loop-driven agents and a `replay` row from the correlator.

**`agent_runs` rows predating migration `20260810_0001` have
`model_provider = NULL`.** That column was added nullable with no backfill,
deliberately: inventing a provider for historical rows would put a guess into an
audit table. Filter on `model_provider IS NOT NULL` when you need rows whose
provenance is known. Around 197 of the rows in a long-lived dev database are in
this state.

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
SBS_API_AGENTS_PIPELINE_ENABLED=true docker compose up -d --force-recreate worker
```

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
