# P0 fix run — report

- **Date:** 2026-08-10
- **Branch:** `fix/handover-p0`, cut from `oss-release-pr` @ `d38e22b`. Not pushed.
- **Input:** [docs/audit/2026-08-10-handover-audit.md](2026-08-10-handover-audit.md); E-numbers below refer to its evidence appendix.
- **Result:** all ten gates green (`stage-a` … `stage-h-full`), 771 passed / 6 skipped.
- **Scope note:** F3 landed **partially, by design** — see F3 below and §Not done.

---

## Gate table

Run end to end after the last commit, against the live compose stack:

```
$ for s in stage-a stage-b stage-c stage-d stage-e stage-f \
           stage-g-contract stage-g-full stage-h-contract stage-h-full; do
    bash scripts/smoke-test-batch.sh $s; done

stage-a            exit=0   10 passed, 1 warning in 5.08s
stage-b            exit=0   7 passed in 4.00s
stage-c            exit=0   7 passed in 4.23s
stage-d            exit=0   27 passed in 5.10s
stage-e            exit=0   8 passed in 0.17s
stage-f            exit=0   25 passed in 0.36s
stage-g-contract   exit=0   84 passed, 1 warning in 10.68s
stage-g-full       exit=0   84 passed, 1 warning in 10.50s  live half: PASS
stage-h-contract   exit=0   35 passed in 2.99s
stage-h-full       exit=0   35 passed in 3.03s  live half: PASS
```

Before this run: `stage-a`, `stage-b`, `stage-c`, `stage-d`, `stage-g-contract` and
`stage-g-full` all failed; `stage-h-*` did not exist (E2.1, E2.3, E2.0).

```
$ uv run pytest -q
771 passed, 6 skipped, 3 warnings in 71.54s (0:01:11)
```

Golden corpus byte-stable across the whole run (`stage-e`/`stage-g` regenerate it):

```
golden checksum before: 1b2345643469a05993990272826624eddcbd3f63ead4bb19b18f5e0791a0dc81  # pragma: allowlist secret
golden checksum after:  1b2345643469a05993990272826624eddcbd3f63ead4bb19b18f5e0791a0dc81  # pragma: allowlist secret
```

**Banned patterns on `*-full`-exclusive paths — zero hits:**

```
$ grep -nE "MockTransport|TestClient|ASGITransport|dependency_overrides|mock\.patch|unittest\.mock|monkeypatch" \
    scripts/smoke_stage_g_live.py scripts/smoke_stage_h_live.py
(no hits — clean)
```

---

## Branch log

```
d6d06dc fix(ui): Anexo 1-A tab renders 27 fields under its "27 campos" heading
8290474 fix(agents): key classify_complaint on the enums the API actually accepts
ea95251 docs(openapi): document POST /v1/sandbox/complaints/granular in the contract
9a935cd fix(scripts): .env supplies defaults to run-api.sh, not overrides
bd5daef fix(tests): implement the stage-h gate pair; stop stage-g-full skipping its live half
5fd605d fix(agents): persist which provider actually served each agent run
9b2dc4e fix(agents): run DIValeVale ahead of Triage on the ingest path
ed2e812 fix(agents): run the Part-12 chain on both canonical ingestion tiers
4fab390 fix(tests): make the Spectral gate step parse Spectral's JSON output
2e8963f fix(db): register the 9 ORM models missing from the metadata graph
```

Ten commits, one per finding plus one for a defect the F1 fix uncovered. Nothing
pushed; the audit report is untouched and uncommitted (`git status` shows only
`?? docs/audit/`).

---

## F1 — Register the 9 missing ORM models (P0-1) — **DONE**

**Before.** `api/sbs_api/db/models/__init__.py` imported 18 of 27 model modules
(E2.5). The `db_schema` fixture builds the test schema with
`Base.metadata.create_all`, so the 9 unimported tables never existed in a test
database and the `fi_brand_aliases` seed errored (E2.2).

**After.** All 9 imported. Guard test `tests/test_orm_model_registry.py` parses every
`__tablename__` under `db/models/` with `ast` — deliberately not by importing, since
import order is the thing being guarded — and asserts each is in `Base.metadata`.

Negative control, proving the guard actually guards (fix temporarily stashed):

```
$ git stash push -q api/sbs_api/db/models/__init__.py
$ uv run pytest -q tests/test_orm_model_registry.py
FAILED tests/test_orm_model_registry.py::test_every_tablename_on_disk_is_registered[digest_audit]
FAILED tests/test_orm_model_registry.py::test_every_tablename_on_disk_is_registered[fi_brand_alias]
FAILED tests/test_orm_model_registry.py::test_every_tablename_on_disk_is_registered[fi_circuit_breaker]
FAILED tests/test_orm_model_registry.py::test_every_tablename_on_disk_is_registered[incident_annotation]
FAILED tests/test_orm_model_registry.py::test_every_tablename_on_disk_is_registered[indecopi_case]
FAILED tests/test_orm_model_registry.py::test_every_tablename_on_disk_is_registered[manual_finding]
FAILED tests/test_orm_model_registry.py::test_every_tablename_on_disk_is_registered[pattern_detection]
FAILED tests/test_orm_model_registry.py::test_every_tablename_on_disk_is_registered[social_signal]
FAILED tests/test_orm_model_registry.py::test_every_tablename_on_disk_is_registered[validation_audit]
9 failed, 19 passed in 0.28s
$ git stash pop -q
$ uv run pytest -q tests/test_orm_model_registry.py
28 passed in 0.33s
```

Gates immediately after F1 (+ the Spectral fix below):

```
stage-a            exit=0  10 passed, 1 warning in 5.49s
stage-b            exit=0  7 passed in 4.23s
stage-c            exit=0  7 passed in 4.45s
stage-d            exit=0  27 passed in 5.12s
stage-g-contract   exit=0  84 passed, 1 warning in 11.16s
```

### Autogenerate check — **NOT a no-op. Reported, not applied.**

As instructed, `alembic revision --autogenerate` was run against the live dev DB
purely as a check, and the generated file inspected then deleted.

```
$ cd api && SBS_API_DATABASE_URL=... uv run alembic revision --autogenerate -m "audit_check_do_not_keep"
INFO  [alembic.autogenerate.compare.tables] Detected removed table 'sector_broadcast_audit'
INFO  [alembic.autogenerate.compare.tables] Detected removed table 'persona_tasks'
...
Generating .../migrations/versions/8d514dd01b52_audit_check_do_not_keep.py ... done

$ grep -nE "op\.drop_table|op\.drop_index" .../8d514dd01b52_audit_check_do_not_keep.py
24: op.drop_index(op.f('ix_sector_broadcasts_status_created'), table_name='sector_broadcasts')
25: op.drop_table('sector_broadcasts')
26: op.drop_index(op.f('ix_sector_broadcast_deliveries_broadcast_target'), table_name='sector_broadcast_deliveries')
27: op.drop_table('sector_broadcast_deliveries')
28: op.drop_index(op.f('ix_sector_broadcast_audit_broadcast_occurred'), table_name='sector_broadcast_audit')
29: op.drop_table('sector_broadcast_audit')
30: op.drop_index(op.f('ix_persona_tasks_assignee_state'), table_name='persona_tasks')
31: op.drop_index(op.f('ix_persona_tasks_creator_created'), table_name='persona_tasks')
32: op.drop_index(op.f('ix_persona_tasks_persona_state'), table_name='persona_tasks')
33: op.drop_table('persona_tasks')
34: op.drop_index(op.f('ix_complaints_flag_unknown_taxonomy'), table_name='complaints')
35: op.drop_index(op.f('ix_institution_certificates_cn'), table_name='institution_certificates')
36: op.drop_index(op.f('ix_institution_certificates_institution_id'), table_name='institution_certificates')
37: op.drop_index(op.f('ix_oauth_clients_institution_id'), table_name='oauth_clients')

$ rm .../8d514dd01b52_audit_check_do_not_keep.py     # deleted, per instruction
$ ls api/migrations/versions/ | wc -l
21                                                    # back to the pre-check count
```

**Diagnosis — a second, distinct gap from the one F1 fixed.** Four tables are
created by migrations and have **no ORM model anywhere in the repo**, not merely an
unimported one:

```
$ grep -rn "__tablename__" api/sbs_api --include="*.py" | grep -E "sector_broadcast|persona_tasks"
(none — no ORM model exists for these 4 tables)

$ grep -rln "sector_broadcasts\|persona_tasks" api/migrations/versions/
api/migrations/versions/20260528_0008_persona_tasks_and_actions.py
api/migrations/versions/20260528_0005_social_and_broadcast.py
```

F1's guard cannot catch these: it walks models on disk, and for these four there is
no model file to walk. The remaining four `drop_index` entries are naming-convention
churn — the same indexes are recreated in `downgrade()` under `op.f()` names.

**No autogenerated migration was applied.** F5's migration is hand-written and
contains no DROP in `upgrade()`, so it was safe to proceed (verified below). Closing
the autogenerate gap properly means authoring four ORM models to match the existing
DDL — outside "small, additive, reviewable" and listed under §Not done.

---

## Spectral gate step — **DONE** (newly discovered, not in the audit)

Fixing F1 unmasked a second defect. `spectral lint --format=json` writes its JSON
array and then a human summary line to the same stream:

```
$ ./node_modules/.bin/spectral lint api/openapi/sbs-api-v1.yaml --format=json | head -c 400
[]No results with a severity of 'error' found!
```

The gate piped that into `python -c 'json.load(sys.stdin)'`, which raised
`JSONDecodeError: Extra data: line 1 column 3 (char 2)` and reported "Spectral
reports errors" on a **clean** spec. The step had never run before: `stage-a`,
`stage-c` and `stage-g-contract` short-circuit on `|| fail` at the pytest step above
it, which was failing for the F1 reason. Adding `-q/--quiet` leaves pure JSON:

```
$ ./node_modules/.bin/spectral lint api/openapi/sbs-api-v1.yaml --format=json --quiet
[]
```

---

## F2 — Agent chain on both canonical ingestion tiers (P0-3) — **DONE**

**Before.** `run_agent_pipeline` had one call site, `demo_ingestion/orchestrator.py`
(E3.5). A Tier-1 submission with the flag on produced zero `agent_runs` rows (E3.3);
Tier 2 never ran the chain at all, which is why
`scripts/run_agent_pipeline_on_new.py` existed as a host-side sweeper (E3.16).

**After.** `api/sbs_api/agents/dispatch.py` is the single entry point both tiers call
after the canonical row commits. Tier 1 attaches it to the 201 as a Starlette
`BackgroundTask` — it runs after the response is on the wire, opens its own session
(the request-scoped one is closed by then) and swallows its own exceptions. Tier 2
calls it per accepted row after the batch transaction commits.

**Tier 1, live, full auth chain (mTLS + OAuth + HMAC, exactly as E3.1):**

```
HTTP/1.1 201 Created
location: /v1/complaints/BCO-2026-428671
x-correlation-id: 2b54f50c-15d6-4051-bce9-690665822ba8

$ psql -c "select agent_name, agent_version, status, started_at, jsonb_array_length(tool_calls) as n_tools
           from agent_runs where complaint_id='BCO-2026-428671' order by started_at;"
 agent_name | agent_version | status  |          started_at           | n_tools
------------+---------------+---------+-------------------------------+---------
 triage     | triage-0.1.0  | success | 2026-08-10 19:01:34.955628+00 |       3

# the dispatch log line carries the request's correlation id
agents.dispatch.completed complaint_id=BCO-2026-428671
  correlation_id=2b54f50c-15d6-4051-bce9-690665822ba8 route_to=info-only tier=tier1
```

**Tier 2, live, processed by the worker container:**

```
HTTP/1.1 202 Accepted
location: /v1/batches/batch_019fed0eb9d37fb191b857d8efc9

$ psql -c "select batch_id, status, row_count_accepted, row_count_rejected from batches where ..."
 batch_019fed0eb9d37fb191b857d8efc9 | complete | 2 | 0

$ psql -c "select complaint_id, agent_name, status, started_at from agent_runs
           where complaint_id in ('COP-2026-229524','COP-2026-229525') ..."
 COP-2026-229524 | triage | success | 2026-08-10 19:03:13.39002+00
 COP-2026-229525 | triage | success | 2026-08-10 19:03:13.399316+00

$ docker logs sbs-worker | grep -o "agents.dispatch.completed.*" | tail -2
agents.dispatch.completed", "level": "info", "timestamp": "2026-08-10T19:03:13.398602Z"}
agents.dispatch.completed", "level": "info", "timestamp": "2026-08-10T19:03:13.401703Z"}
```

`docker-compose.yaml` now passes `SBS_API_AGENTS_PIPELINE_ENABLED` and
`SBS_API_MODEL_PROVIDER` through to the worker, **defaulted to today's values**
(`false` / `on_prem`) so compose behaviour is unchanged unless an operator opts in.

### Config coherence (P1-5) — **DONE**

`providers/__init__.py` read `SBS_API_MODEL_PROVIDER` with a bare `os.getenv`,
bypassing `Settings` (E1.5). Resolution now goes through
`Settings.agents_pipeline_provider`, whose `AliasChoices` accepts both
`SBS_API_MODEL_PROVIDER` (checked first, the documented name) and
`SBS_API_AGENTS_PIPELINE_PROVIDER`. `import os` is gone from that module.

A fresh `Settings()` — not the `lru_cache`-d `get_settings()` — is constructed on
resolution, because `reset_provider_cache()` is the documented way to switch
providers mid-process and a cached `Settings` would pin the import-time value. The
existing provider tests, which `monkeypatch.setenv` then call `get_provider()`, pass
unchanged:

```
$ uv run pytest -q tests/test_agent_providers.py
11 passed in 0.23s
```

`.env.example` now documents the wired variable and the alias.

---

## F3 — DIValeVale ahead of Triage (P0-5) — **PARTIAL, deliberately**

**Done:** DIValeVale now runs on the real ingestion path, ahead of Triage, and writes
one `validation_audit` row per ingested complaint. `api/sbs_api/agents/ingest_entry.py`
holds the ordering; both tiers reach it through F2's dispatcher.

```
$ psql -tAc "select count(*) from validation_audit;"     # before
0
# ... signed POST /v1/complaints ...
$ psql -tAc "select count(*) from validation_audit;"     # after
1

$ psql -x -c "select * from validation_audit where complaint_id='BCO-2026-931967';"
audit_id           | 35a613e9-b599-4e32-b4f0-8b33cc7dc620
complaint_id       | BCO-2026-931967
institution_code   | SBS-001234
received_at        | 2026-08-10 19:07:30.073866+00
verdict            | INVALID
pass1_failed_rules | {INSTITUTION_CODE_INVALID,AMOUNT_CLAIMED_MISSING}
routing_action     | REJECTED
tier               | TIER_1
```

Ordering — validation completes before the dispatch that runs triage:

```
19:07:30.080  agents.validation.recorded  complaint_id=BCO-2026-931967 verdict=INVALID
              routing_action=REJECTED failed_rules=INSTITUTION_CODE_INVALID,AMOUNT_CLAIMED_MISSING
              enforced=False
19:07:30.149  agents.dispatch.completed   complaint_id=BCO-2026-931967 tier=tier1
              validation_verdict=INVALID route_to=info-only
```

**Not done: the verdict does not gate Triage, and enrichment side effects are
suppressed** (new `record_only` flag, default `False`, so every existing caller is
untouched). Two verifiable blockers, both measured rather than assumed:

**1. The institution-identifier contract is unreconciled.** Pass 1 requires
`institution_code` matching `^[A-Z]{3}_[A-Z]+_\d{3}$`. Measured verdicts for a real
canonical record:

```
institution_code=SBS-001234 (what every surface issues)  verdict=INVALID       failed=['INSTITUTION_CODE_INVALID', 'AMOUNT_CLAIMED_MISSING']
institution_code=BANCO_DEMO_001 (dev-seed alias)         verdict=INVALID       failed=['INSTITUTION_CODE_INVALID', 'AMOUNT_CLAIMED_MISSING']
institution_code=BCO_DEMO_001 (DIValeVale tests only)    verdict=INSUFFICIENT  failed=['AMOUNT_CLAIMED_MISSING']
...+ amount in narrative                                 verdict=RECOVERABLE   recoverable=['amount_claimed']
...+ amount_claimed + currency supplied                  verdict=VALID         failed=[]
```

No `institution_id → institution_code` mapping exists in the code or the database:

```
$ grep -rhoE '"[A-Z]{3}_[A-Z]+_[0-9]{3}"' tests/ api/ scripts/ | sort | uniq -c
  13 "BCO_DEMO_001"          # all 13 inside DIValeVale's own tests
$ psql -c "select * from fi_circuit_breakers;"
(0 rows)
```

**2. The canonical Tier-1 schema cannot carry what Pass 1 wants.** ADR 0026 fixes
Tier 1 at a 15-field Anexo 1-A subset with no `amount_claimed` and no `currency`. For
the `COBRO_INDEBIDO` family — where Pass 1 requires an amount — every legitimate
record therefore lands on INSUFFICIENT, whose routing action is
FLAGGED_FOR_ENRICHMENT, which calls `_flag_for_enrichment` → `deliver_enrichment_request`:
**an outbound webhook to the institution, one per complaint filed.**

Enforcing the verdict today would either stop Triage on every real Tier-1 record
(regressing F2, which is verified working) or spam institutions with spurious
resubmission requests. Supplying a placeholder `institution_code` or a default
currency would put fabricated values into a regulator-facing audit table, so the
adapter omits absent fields and the gap shows honestly in `pass1_failed_rules`. A
test pins that:

```python
def test_validation_record_adapter_invents_no_fields(...):
    assert "amount_claimed" not in mapped
    assert "currency" not in mapped
```

Confirmed no side effect fired: `select count(*) from enrichment_requests;` → `0`.

Flipping this to a gate needs (1) an authoritative institution-code mapping and (2)
an ADR 0026 decision on whether amount and currency join the Tier-1 schema. Both are
recorded in §Not done.

---

## F4 — stage-h pair; stage-g-full sequencing (P0-2) — **DONE**

**Before.** `tests/test_demo_determinism.py` referenced `stage-h-full` /
`stage-h-contract`; neither existed, and the runner's usage string stopped at
`stage-g-full` (E2.0). `stage-g-full` ran the contract half with `|| fail`, so a
contract regression skipped the only live assertion in the gate (E2.3).

**After.** Both halves of `stage-g-full` and `stage-h-full` always run, each half's
result is printed, and the gate exits non-zero if either failed.

`stage-h-full` (`scripts/smoke_stage_h_live.py`) is a live gate with no in-process
shortcuts — real TLS connections made by curl, assertions read from the live DB:

```
[15:40:31] compose services up: ['keycloak', 'postgres', 'redis', 'webhook-listener', 'worker']
[15:40:31] worker has the agent pipeline enabled
[15:40:31] API reachable over mTLS at https://sbs-suptech-sandbox.local:8443
[15:40:31] --- Tier 1: signed POST /v1/complaints ---
[15:40:31] tier 1: 201 Created BCO-2026-390831
[15:40:31] tier1: validation_audit verdict=INVALID action=REJECTED
[15:40:31] tier1: agent_runs triage(status=success,provider=mock)
[15:40:31] --- Tier 2: signed POST /v1/batches (worker container) ---
[15:40:31] tier 2: 202 Accepted batch_019fed30e29d75419d6636b94286 (1 row)
[15:40:32] batch complete: accepted=1
[15:40:32] tier2: validation_audit verdict=INVALID action=REJECTED
[15:40:32] tier2: agent_runs triage(status=success,provider=mock)
[15:40:32] stage-h-full live assertion: PASS

  contract half: PASS
  live half:     PASS
stage-h-full: PASS
```

The Tier-2 agent run in that trace executed **inside the worker container**, reached
over the docker network via Redis and Postgres.

**The new gate immediately earned its keep.** Its first run failed — correctly —
because the worker container was still running pre-F3 code:

```
[15:39:34] FAIL: tier2: DIValeVale did not run for COP-2026-390773 — no validation_audit row
                 (it must run ahead of triage)
  contract half: PASS
  live half:     FAIL
FAIL: stage-h-full: contract_rc=0 live_rc=1
```

After `docker compose up -d --force-recreate worker`, it passed. A gate that only
ever passes proves nothing; this one caught a real staleness bug on its first
outing.

`stage-g-full`, with the new sequencing:

```
[19:41:03] batch complete: accepted=3, rejected=0
[19:41:04] listener PASS line present for batch batch_019fed315bfd7f62b01913ff50cd
[19:41:04] stage-g-full live assertion: PASS

  contract half: PASS
  live half:     PASS
stage-g-full: PASS
```

---

## F5 — Persist provider identity (P1-4) — **DONE**

**Before.** `agent_runs` had no provider column (E3.15); that a mock rather than a
model produced an output survived only in stderr (E3.11).

**After.** `ModelResponse.served_by` is set by each provider to its own name. The
`on_prem` fallback returns `MockProvider`'s response unchanged, so a fallback
naturally reports the **effective** provider, not the configured one. `run_loop`
carries it to `LoopResult`; the four loop-driven agents pass it to
`finish_agent_run`.

Migration `20260810_0001` is additive — one nullable `String(16)`, no backfill — and
was hand-written, not autogenerated:

```
$ awk '/^def upgrade/,/^def downgrade/' api/migrations/versions/20260810_0001_*.py | grep -c drop
0 drops in upgrade — safe to apply

$ cd api && uv run alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade 20260529_0002 -> 20260810_0001,
      Record which provider actually served each agent run.

$ psql -c "\d agent_runs"
 model_provider | character varying(16) |  |  |
```

The column discriminates rather than recording a constant. Fallback case:

```
$ psql -c "select complaint_id, agent_name, status, model_provider from agent_runs where complaint_id='BCO-2026-936134';"
 BCO-2026-936134 | triage | success | mock
```

Replay case, and mixed providers within one complaint:

```
$ psql -c "select agent_name, status, model_provider from agent_runs where complaint_id='BCO-2026-000001' ...;"
 cross-source-correlator | success | replay
 synthesis               | success | replay
 investigation           | success | replay
 triage                  | success | replay

$ psql -c "select agent_name, status, model_provider, final_output->>'route_to' from agent_runs where complaint_id='BCO-2026-850088' ...;"
 triage                  | success | mock   | investigation
 investigation           | success | mock   |
 synthesis               | success | mock   |
 cross-source-correlator | success | replay |      ← replay-driven agent, correctly distinguished
```

`docs/schemas/agent_run.schema.json` and `agent_run.md` document the field as
optional so exports predating it still validate.
`tests/test_alembic_migration.py`'s head-revision pin was updated to `20260810_0001`.

---

## F6 — `run-api.sh` env precedence (P1-1) — **DONE**

**Before.** `set -a; . ./.env; set +a` ran after the caller's exports, so `.env` won
(E1.4).

**After.** The caller's environment is snapshotted with `export -p` and re-applied
after sourcing: caller wins, `.env`-only values are still picked up, a fresh clone
with no `.env` is unaffected.

```
--- A: caller exports direct (README step 2) ---
effective SBS_API_MTLS_MODE=[direct]  AUTH_STUB=[false]
value only .env sets (INTERNAL_API_SECRET) still present: yes
--- B: caller exports nothing (.env default applies) ---
effective SBS_API_MTLS_MODE=[proxy]
```

End to end, with this machine's `.env` (`SBS_API_MTLS_MODE=proxy`) present —
README step 2 run literally, then README step 3 against it:

```
$ SBS_API_MTLS_MODE=direct SBS_API_AUTH_STUB_ENABLED=false SBS_API_PORT=8443 bash scripts/run-api.sh
==> mTLS direct mode: uvicorn will require client certs signed by dev-ca/ca.pem
INFO:     Uvicorn running on https://0.0.0.0:8443 (Press CTRL+C to quit)

$ bash scripts/smoke-test-auth.sh ; echo "exit=$?"
  mTLS handshake + liveness OK
  cnf.x5t#S256 binding OK
  201 Created OK
  SIGNATURE_REPLAYED OK
  429 + 4 rate-limit headers OK
All auth-chain smoke-test assertions passed.
exit=0
```

---

## F7 — Granular route in the canonical contract (P0-4) — **DONE**

Added `POST /v1/sandbox/complaints/granular` to `api/openapi/sbs-api-v1.yaml` with a
`Sandbox (Institution)` tag and the two component schemas it references. The
description states the two differences from the canonical Tier-1 route (richer
payload, synchronous receipt) and notes that both persist the same canonical record
and — now that F2 exists — run the same agent chain under the same flag.

```
$ ./node_modules/.bin/spectral lint api/openapi/sbs-api-v1.yaml --format=json --quiet \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('errors:', len([r for r in d if r.get('severity')==0]), 'warnings:', len([r for r in d if r.get('severity')==1]))"
errors: 0 warnings: 0

$ uv run pytest -q tests/ -k "openapi or spec or contract"
72 passed, 705 deselected in 5.01s

# present in the spec the running API actually serves:
$ curl -s ... https://sbs-suptech-sandbox.local:8443/v1/openapi.yaml | grep -c "sandbox/complaints/granular"
1
```

---

## F8 — `classify_complaint` on the real enum space (P2-2) — **DONE**

**Before.** `RULES_TABLE` held only prompt-era keys (`credit-card`,
`undisclosed-fee`) while the API accepts `TARJETA_CREDITO` / `COBRO_INDEBIDO`
(E3.17), so every real complaint fell through to `other @ 0.55` (E3.6).

**After.** A canonical block keyed on the real `ProductCategory` / `MotivoCode`
values, reusing the existing labels and confidence bands. The prompt-era keys are
retained — `tests/integration/test_agent_pipeline.py` and the seeded demo rows still
use them. The `BCO-2026-000001` invariant is untouched; `model_id` stays `rules-v1`.

Live signed submission, `TARJETA_CREDITO` + `COBRO_INDEBIDO`:

```
classification | { "label": "undisclosed-fees-credit",
               |   "model_id": "rules-v1",
               |   "confidence": 0.82,
               |   "alternatives": [] }
model_provider | mock
```

Downstream effect — 0.82 routes to investigation, so the chain now runs to depth on a
real Tier-1 complaint where it previously stopped at triage with `info-only`:

```
 triage                  | success | mock   | investigation
 investigation           | success | mock   |
 synthesis               | success | mock   |
 cross-source-correlator | success | replay |
```

---

## F9 — 27-field table (P2-1) — **DONE**

Dropped the `EMPRESA` row: it is column 28 of the source spreadsheet, but the API
derives the reporting entity from the authenticated caller (OAuth subject + mTLS
cert), so an institution never supplies it. A comment records that derivation and the
23 + 1 + 3 numbering the DQ rules assert.

```
$ awk '/^function AnnexTab/,/^  \];/' app/src/components/docs/DocsTabs.tsx | grep -c "{ key: '"
27
$ awk '/^function AnnexTab/,/^  \];/' app/src/components/docs/DocsTabs.tsx | grep -c "EMPRESA"
0
$ cd app && npx tsc --noEmit ; echo "tsc exit=$?"
tsc exit=0
```

Heading and table now agree at 27. Verified at the source + typecheck level; the tab
body is client-rendered, so it is not present in the server HTML to grep (see
§Caveats).

---

## Not done / newly discovered

1. **Four tables have no ORM model at all** — `sector_broadcasts`,
   `sector_broadcast_deliveries`, `sector_broadcast_audit`, `persona_tasks`. Created
   by migrations `20260528_0005` and `20260528_0008`; autogenerate would DROP them
   (evidence under F1). Distinct from P0-1 and not catchable by F1's guard, which
   walks model files. **This is the single highest-value follow-up**: until it is
   closed, `alembic revision --autogenerate` remains unsafe on this repo. Fixing it
   means authoring four ORM models against the existing DDL, then extending the guard
   to compare `op.create_table` calls in `migrations/versions/` against
   `Base.metadata`.
2. **F3 is not a gate** — DIValeVale records but does not enforce. Needs an
   authoritative `institution_id → institution_code` mapping and an ADR 0026 decision
   on `amount_claimed` / `currency` in the Tier-1 schema. Full evidence under F3.
3. **`scripts/run_agent_pipeline_on_new.py` is no longer load-bearing** but was left
   in place — it is still useful for backfilling complaints ingested while the flag
   was off. Its docstring now overstates its necessity.
4. **Untouched P1s from the audit** (out of this run's scope list): P1-2 (README
   never explains how to start the cockpit or Keycloak), P1-3 (`institution-api-workflow.md`
   gives the wrong cockpit URL — `/supervisor` 404s, the real path is `/app/cockpit`),
   P1-6 (root `.env.example` omits `SBS_API_INTERNAL_API_SECRET`), P1-7 (cockpit
   journey routes shell out to a hard-coded `./.venv/bin/python`), P1-8 (`app/README.md`
   says "Five screens"; there are ~20 routes).
5. **ADR 0001 roster drift** — it names five agents; the locked registry holds six
   with different membership. Not touched here; one paragraph of ADR maintenance.
6. **The audit's P2-3 and P2-4 remain**: `rank_features` still returns a constant
   `DEFAULT_FEATURES` list under `xgboost-replay-v1`, and the investigation draft
   narrative still renders `clasificación inicial '—'` for records whose
   classification is absent. Neither was in scope.

## Caveats on this run's evidence

- **No real vLLM was available**, so every live model call was served by
  `MockProvider` via the `on_prem` fallback. `model_provider` was proven to
  discriminate using `replay` vs `mock` (F5), but the `on_prem` value has not been
  observed from a genuine vLLM completion.
- **F9 was verified at source + typecheck level.** The Annex tab renders client-side,
  so the 27 rows are not in the server HTML; `curl` of `/app/docs` returns 200 but
  contains no field keys to count.
- **`stage-h-full` requires operator setup** — worker started with
  `SBS_API_AGENTS_PIPELINE_ENABLED=true` and the API running with mTLS on :8443 with
  the pipeline enabled. The gate checks both pre-conditions and fails with the exact
  fix command rather than timing out; it is not self-provisioning.
- **The worker container mounts the repo read-only and must be recreated** to pick up
  code changes. `stage-h-full` caught this once already; a vendor changing agent code
  will hit the same thing.

## Session state

- Both stale uvicorns from the audit run (`:8443`, `:8000`) were stopped at the start
  of this run, identified by port. `next dev` on `:3000` and the compose stack were
  left alone, as instructed.
- One API is running on `:8443`, started via `scripts/run-api.sh` for the F6/F8
  verification. The `sbs-worker` container was recreated with
  `SBS_API_AGENTS_PIPELINE_ENABLED=true` and `SBS_API_MODEL_PROVIDER=mock`; a plain
  `docker compose up -d worker` returns it to the default-off posture.
- Working tree is clean apart from untracked `docs/audit/`. Nothing was pushed. The
  audit report was neither modified nor committed. All ten commits passed pre-commit
  hooks; `--no-verify` was not used.
