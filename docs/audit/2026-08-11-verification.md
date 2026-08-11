# Independent verification — 2026-08-11

- **Date:** 2026-08-11
- **Branch:** `fix/handover-p0` @ `107d56f`. Nothing committed, nothing pushed, no tracked file modified.
- **Inputs treated as hypotheses, not facts:**
  [2026-08-10-handover-audit.md](2026-08-10-handover-audit.md),
  [2026-08-10-p0-fix-report.md](2026-08-10-p0-fix-report.md),
  [2026-08-11-f10-report.md](2026-08-11-f10-report.md).
- **Method:** runtime state rebuilt from cold (`docker compose down` without `-v`,
  `docker compose up -d`, worker force-recreated with the pipeline on and the mock
  provider, API started through `scripts/run-api.sh`), then every claim re-measured.
- **Headline:** every gate and test claim in the two fix reports **reproduces exactly**.
  Two claims about *documentation* do not, one of them a defect neither report lists.
  The `MockProvider` cursor defect F10 self-reported is **confirmed and reproduced**,
  and it is the single reason for the recommendation below.
- **Recommendation: NO-GO** for handover today. Three specific blockers, all small.
  See §Recommendation.

---

## 1. Gates, tests, banned patterns

### Gate table — all ten green

```
$ for s in stage-a stage-b stage-c stage-d stage-e stage-f \
           stage-g-contract stage-g-full stage-h-contract stage-h-full; do
    bash scripts/smoke-test-batch.sh $s; done

stage-a            exit=0   11 passed, 2 warnings in 5.67s
stage-b            exit=0   7 passed in 3.95s
stage-c            exit=0   7 passed in 4.26s
stage-d            exit=0   27 passed in 5.07s
stage-e            exit=0   8 passed in 0.15s
stage-f            exit=0   25 passed in 0.35s
stage-g-contract   exit=0   85 passed, 2 warnings in 11.55s
stage-g-full       exit=0   85 passed, 2 warnings in 11.66s  live half: PASS
stage-h-contract   exit=0   37 passed in 3.14s
stage-h-full       exit=0   37 passed in 3.03s  live half: PASS
```

**PASS.** Assertion counts are identical, gate for gate, to the F10 report's table
(11/7/7/27/8/25/85/85/37/37). No discrepancy.

`stage-h-full` live half, verbatim:

```
[11:27:49] compose services up: ['keycloak', 'postgres', 'redis', 'webhook-listener', 'worker']
[11:27:49] worker has the agent pipeline enabled
[11:27:49] API reachable over mTLS at https://sbs-suptech-sandbox.local:8443
[11:27:49] --- Tier 1: signed POST /v1/complaints ---
[11:27:49] tier 1: 201 Created BCO-2026-462069
[11:27:50] tier1: validation_audit verdict=INVALID action=REJECTED
[11:27:50] tier1: agent_runs triage(status=success,provider=mock), investigation(status=success,provider=mock), synthesis(status=success,provider=mock), cross-source-correlator(status=success,provider=replay)
[11:27:50] --- Tier 2: signed POST /v1/batches (worker container) ---
[11:27:50] tier 2: 202 Accepted batch_019ff16fe6d470c2a1590d3e1bb0 (1 row)
[11:27:51] batch complete: accepted=1
[11:27:51] tier2: validation_audit verdict=INVALID action=REJECTED
[11:27:51] tier2: agent_runs triage(status=success,provider=mock)
[11:27:51] stage-h-full live assertion: PASS

  contract half: PASS
  live half:     PASS
stage-h-full: PASS
```

### Full suite

```
$ uv run pytest -q
774 passed, 6 skipped, 4 warnings in 75.04s (0:01:15)
```

**PASS** — exactly the F10 report's figure.

### Golden corpus

```
golden checksum before: 1b2345643469a05993990272826624eddcbd3f63ead4bb19b18f5e0791a0dc81  # pragma: allowlist secret
golden checksum after:  1b2345643469a05993990272826624eddcbd3f63ead4bb19b18f5e0791a0dc81  # pragma: allowlist secret
```

**PASS.** Byte-stable across the run and identical to the value in both prior reports.

### Banned patterns on the `*-full`-exclusive paths

```
$ grep -nE "MockTransport|TestClient|ASGITransport|dependency_overrides|mock\.patch|unittest\.mock|monkeypatch" \
    scripts/smoke_stage_g_live.py scripts/smoke_stage_h_live.py
grep_exit=1        # 1 = no hits
```

**PASS** — zero hits, as claimed.

---

## 2. Demo path from cold — PASS, with one undocumented prerequisite

Method per the audit's E3.1 / E3.19: mTLS client cert + OAuth client-credentials
token + HMAC-SHA256 over the ADR 0027 canonical request, driven by curl from a
script outside the app process. Every assertion below is a live DB read.

### Tier 1 — `POST /v1/complaints`

```
HTTP/1.1 201 Created
location: /v1/complaints/BCO-2026-462222
etag: "abc5f138eae49cb435ed8216"  # pragma: allowlist secret
x-ratelimit-limit: 1000
x-ratelimit-remaining: 999
x-correlation-id: 47ae44f7-ee53-4835-b92d-1f0f59cb75d2
traceparent: 00-b4259afaf2260ca1c44c1e349f445270-7b876d99b928646d-01

{"complaint_id":"BCO-2026-462222","institution_id":"SBS-001234","received_at":"2026-08-11T15:30:22.209434Z","resolution_status":"pendiente","client_submission_id":null}
```

**Correlation ID: `47ae44f7-ee53-4835-b92d-1f0f59cb75d2`.**

### Tier 2 — `POST /v1/batches`

```
HTTP/1.1 202 Accepted
location: /v1/batches/batch_019ff172381275e191f6e0d353eb
x-correlation-id: 3d867ceb-3d06-490c-ac6e-0026354972d0
traceparent: 00-3279b0c986f25b7042516271d8898dde-2e3a0e5bf2fa51b0-01

{"batch_id":"batch_019ff172381275e191f6e0d353eb","status":"pending"}
```

**Correlation ID: `3d867ceb-3d06-490c-ac6e-0026354972d0`.** Processed by the worker
container:

```
              batch_id              |  status  | row_count_accepted | row_count_rejected
------------------------------------+----------+--------------------+--------------------
 batch_019ff172381275e191f6e0d353eb | complete |                  1 |                  0
```

Both tiers land as the same canonical record, distinguished only by `source`:

```
  complaint_id   | institution_id |    source    | product_category |  motivo_code   | severity | resolution_status
-----------------+----------------+--------------+------------------+----------------+----------+-------------------
 BCO-2026-462222 | SBS-001234     | api_realtime | TARJETA_CREDITO  | COBRO_INDEBIDO | HIGH     | pendiente
 COP-2026-462222 | SBS-005678     | batch        | TARJETA_CREDITO  | COBRO_INDEBIDO | HIGH     | pendiente
```

### `validation_audit` timestamped BEFORE the triage run — PASS

Not asserted by eye; computed in SQL:

```sql
select v.complaint_id, v.received_at as validation_at, min(a.started_at) as first_agent_run_at,
       (v.received_at < min(a.started_at)) as validation_ran_first,
       min(a.started_at) - v.received_at as delta
from validation_audit v join agent_runs a using (complaint_id)
where v.complaint_id in ('BCO-2026-462222','COP-2026-462222') group by 1,2;
```

```
  complaint_id   |         validation_at         |      first_agent_run_at       | validation_ran_first |      delta
-----------------+-------------------------------+-------------------------------+----------------------+-----------------
 BCO-2026-462222 | 2026-08-11 15:30:22.266258+00 | 2026-08-11 15:30:22.283846+00 | t                    | 00:00:00.017588
 COP-2026-462222 | 2026-08-11 15:30:22.811005+00 | 2026-08-11 15:30:22.813036+00 | t                    | 00:00:00.002031
```

Verdicts: `INVALID` / `REJECTED` on both tiers — consistent with F3's documented
record-only posture, and `select count(*) from enrichment_requests` is still **0**,
so no outbound side effect fired.

### `agent_runs` with `model_provider` populated — PASS

```
  complaint_id   |       agent_name        | status  | model_provider |          started_at           | n_tools
-----------------+-------------------------+---------+----------------+-------------------------------+---------
 BCO-2026-462222 | triage                  | success | mock           | 2026-08-11 15:30:22.283846+00 |       3
 BCO-2026-462222 | investigation           | success | mock           | 2026-08-11 15:30:22.317559+00 |       4
 BCO-2026-462222 | synthesis               | success | mock           | 2026-08-11 15:30:22.322679+00 |       2
 BCO-2026-462222 | cross-source-correlator | success | replay         | 2026-08-11 15:30:22.329635+00 |       2
 COP-2026-462222 | triage                  | success | mock           | 2026-08-11 15:30:22.813036+00 |       0
```

Provider identity is persisted and discriminates (`mock` vs `replay`) within one
complaint. **But note `n_tools=0` on the Tier-2 row** — that is the cursor defect,
quantified in §6.2. Column-wide: 53 `mock`, 14 `replay`, 197 NULL (all pre-F5 rows;
F5's migration is additive with no backfill, exactly as documented).

### Rendered by `/app/cockpit` with a real session — PASS, after an extra step

Session obtained through `GET /app/api/auth/demo-login`, which redirects to
`/app/cockpit` rather than `/app/login?error=demo_login_failed` — i.e.
`loadAllPersonaTokens()` succeeded, so the session is genuinely Keycloak-ROPC-backed
(the realm answers `http=200` on `.well-known/openid-configuration`; the container
healthcheck reports `unhealthy` but the realm is functional — see §UNVERIFIED).

```
/app/cockpit   http=200 bytes=91927   tier1_hits=1  tier2_hits=1
/app/findings  http=200 bytes=203693  tier1_hits=1  tier2_hits=1
/app/audit     http=200 bytes=222792  tier1_hits=9  tier2_hits=3
```

`/app/cockpit` renders **both** the Tier-1 and the Tier-2 record submitted in this
run. **PASS.**

**The extra step, and it is a finding.** `app/.env.local` points the cockpit's
server-side fetches at `SBS_INTERNAL_API_BASE_URL=http://localhost:8000`. The cold
rebuild described in both reports' §Session state brings up **one** API, on `:8443`.
In that state, with a real session:

```
$ curl -H "Cookie: sbs-session=…" http://localhost:3000/app/cockpit
http=500 bytes=9938        # page body contains "fetch failed"
tier1 hits: 0   tier2 hits: 0
$ lsof -nP -iTCP:8000 -sTCP:LISTEN
(nothing on :8000)
```

The cockpit only renders once a **second** API process is started on `:8000`
(`SBS_API_PORT=8000 bash scripts/run-api.sh`, auth-stub on, plain HTTP). No README,
no report §Session state, and no gate mentions that the demo needs two API processes
on two ports with two different auth postures. This is a sharper, concrete instance
of the audit's P1-2 and it is **not stated anywhere**: the prior sessions each had a
`:8000` uvicorn already running from earlier work, so it never surfaced as a
prerequisite.

---

## 3. README walk, steps 1–3 literally, with this machine's `.env` present — **FAIL at step 3**

`.env` present (550 bytes) and contains `SBS_API_MTLS_MODE=proxy` — the trap.

### Step 1 — `bash scripts/dev-up.sh` — PASS

```
==> alembic upgrade head
==> seeding demo institutions
    institutions: SBS-001234 (BANCO_DEMO_001), SBS-005678 (COOPAC_DEMO_002)
==> seeding institution_certificates from dev-ca/seed-certificates.sql
==> seeding oauth_clients (argon2id hashes)
    oauth_clients: banco-demo-001 (SBS-001234), coopac-demo-002 (SBS-005678)
==> ready
DSN: postgresql+asyncpg://sbs:sbs@localhost:5432/sbs_dev  # pragma: allowlist secret
```

### Step 2 — verbatim from README lines 21–23 — F6's fix WORKS, but the step is incomplete

```
$ SBS_API_MTLS_MODE=direct \
  SBS_API_AUTH_STUB_ENABLED=false \
    bash scripts/run-api.sh

==> mTLS direct mode: uvicorn will require client certs signed by dev-ca/ca.pem
INFO:     Uvicorn running on https://0.0.0.0:8000 (Press CTRL+C to quit)
[info] app_started  api_version=0.1.0 auth_stub_enabled=False environment=dev
```

**F6 verified.** With `.env` setting `proxy`, the caller's `direct` won and
`auth_stub_enabled=False` held — the P1-1 precedence bug is genuinely fixed. Note
the port: **`:8000`**, because README step 2 does not export `SBS_API_PORT`.

### Step 3 — `bash scripts/smoke-test-auth.sh` — **FAIL, exit 7**

```
==> 0. liveness via mTLS
curl: (7) Failed to connect to sbs-suptech-sandbox.local port 8443 after 0 ms: Couldn't connect to server
README step 3 exit=7
```

`scripts/smoke-test-auth.sh` hard-defaults `PORT="${SBS_API_PORT:-8443}"` (line 41);
README step 2 leaves the API on the `__main__.py` default of `8000`. The two steps
cannot meet.

**Control — the same script against an API started with the port added:**

```
$ SBS_API_MTLS_MODE=direct SBS_API_AUTH_STUB_ENABLED=false SBS_API_PORT=8443 … bash scripts/run-api.sh
$ bash scripts/smoke-test-auth.sh ; echo exit=$?
  mTLS handshake + liveness OK
  cnf.x5t#S256 binding OK
  201 Created OK
  SIGNATURE_REPLAYED OK
  429 + 4 rate-limit headers OK
All auth-chain smoke-test assertions passed.
exit=0
```

**Discrepancy against the P0 fix report.** Its F6 section says *"End to end, with this
machine's `.env` … present — README step 2 run literally, then README step 3 against
it"* and then shows a transcript containing `SBS_API_PORT=8443`. That variable is not
in README step 2. F6 fixed the `.env` precedence bug it set out to fix, and its
A/B evidence for that is sound; but the README's advertised three-command path still
does not work, and F6's wording implies it does. This is a **new defect**, on neither
report's open list.

Cockpit bootstrap gaps (P1-2 / P1-3) are noted, not fixed, per instruction — and §2
adds the two-API-process requirement to that pile.

---

## 4. Alembic autogenerate check — PASS, zero table-level operations

```
$ ls api/migrations/versions/*.py | wc -l        →  21   (before)
$ psql -tAc "select version_num from alembic_version;"   →  20260810_0001

$ cd api && SBS_API_DATABASE_URL=postgresql+asyncpg://sbs:sbs@localhost:5432/sbs_dev \  # pragma: allowlist secret
    uv run alembic revision --autogenerate -m "verify_check_do_not_keep"
INFO  [alembic.autogenerate.compare.constraints] Detected removed index 'ix_complaints_flag_unknown_taxonomy' on 'complaints'
INFO  [alembic.autogenerate.compare.constraints] Detected removed index 'ix_institution_certificates_cn' on 'institution_certificates'
INFO  [alembic.autogenerate.compare.constraints] Detected removed index 'ix_institution_certificates_institution_id' on 'institution_certificates'
INFO  [alembic.autogenerate.compare.constraints] Detected removed index 'ix_oauth_clients_institution_id' on 'oauth_clients'
Generating .../migrations/versions/f77f59abde6e_verify_check_do_not_keep.py ...  done
```

**No `Detected removed table` line.** The generated file in full:

```python
def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_complaints_flag_unknown_taxonomy'), table_name='complaints')
    op.drop_index(op.f('ix_institution_certificates_cn'), table_name='institution_certificates')
    op.drop_index(op.f('ix_institution_certificates_institution_id'), table_name='institution_certificates')
    op.drop_index(op.f('ix_oauth_clients_institution_id'), table_name='oauth_clients')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_index(op.f('ix_oauth_clients_institution_id'), 'oauth_clients', ['institution_id'], unique=False)
    op.create_index(op.f('ix_institution_certificates_institution_id'), 'institution_certificates', ['institution_id'], unique=False)
    op.create_index(op.f('ix_institution_certificates_cn'), 'institution_certificates', ['cn'], unique=False)
    op.create_index(op.f('ix_complaints_flag_unknown_taxonomy'), 'complaints', ['flag_unknown_taxonomy'], unique=False)
    # ### end Alembic commands ###
```

Operation counts on that file:

```
  op.drop_table:                0
  op.create_table:              0
  op.drop_column:               0
  op.add_column:                0
  op.alter_column:              0
  op.drop_constraint:           0
  op.create_check_constraint:   0
  op.drop_index:                4
  op.create_index:              4
  table-level operations total: 0
```

Inspected, **deleted, never applied**:

```
$ rm api/migrations/versions/f77f59abde6e_verify_check_do_not_keep.py
$ ls api/migrations/versions/*.py | wc -l   →  21
$ git status --short                        →  ?? docs/audit/
```

**PASS.** F10's post-fix expectation holds exactly: no table can be dropped, four
spurious `drop_index` lines remain, so a generated migration still has to be read
before use. F10a's final-paragraph caveat is accurate.

---

## 5. Contract — PASS

```
$ curl … https://sbs-suptech-sandbox.local:8443/v1/openapi.yaml -o served.yaml
http=200 bytes=58212
$ grep -n "sandbox/complaints/granular" served.yaml
428:  /sandbox/complaints/granular:
$ shasum -a 256 served.yaml api/openapi/sbs-api-v1.yaml
3aa32675783b164aea6ddec84b53e146afc0d7f83c0fad3da575a8834dc03f13  served.yaml
3aa32675783b164aea6ddec84b53e146afc0d7f83c0fad3da575a8834dc03f13  api/openapi/sbs-api-v1.yaml
```

The spec the running API serves is byte-identical to the repo contract and contains
the granular route (F7 verified, and one step stronger than F7's `grep -c`).

```
$ ./node_modules/.bin/spectral lint api/openapi/sbs-api-v1.yaml --format=json --quiet
[]
spectral_exit=0
```

**PASS** — clean, zero errors, zero warnings.

---

## 6. Spot-checks against reality

### 6.1 The named claim — cross-source-correlator, `provider=replay`, non-demo complaints

**Verdict: F5/F8 are right; the original audit is wrong. Both reports omit a nuance.**

Reproduced live on a fresh non-demo complaint (§2): `cross-source-correlator`,
`status=success`, `model_provider=replay`, 2 tool calls, for `BCO-2026-462222`. It
does **not** skip.

The mechanism, which neither report states: `ReplayProvider._load` falls back to a
generic `_default.json` before raising:

```python
path = self._root / agent_name / f"{complaint_id}.json"
if not path.exists():
    # Generic default fixture lets the runtime exercise an agent
    # without a complaint-specific recording.
    default = self._root / agent_name / "_default.json"
    if not default.exists():
        raise ReplayFixtureMissing(...)
    path = default
```

A `_default.json` exists for **all four** agents, and has since the original
agent-layer commit — long before the audit, untouched on this branch:

```
$ ls api/sbs_api/agents/fixtures/replay/*/_default.json
  cross-source-correlator/_default.json   investigation/_default.json
  synthesis/_default.json                 triage/_default.json
$ git log --oneline --follow -- .../cross-source-correlator/_default.json
34a939b feat(p12): agent layer — 3 real agents, 2 scaffolded, 10 tools, provider-pluggable
$ for f in triage synthesis investigation cross-source-correlator; do
    git cat-file -e "d38e22b:api/sbs_api/agents/fixtures/replay/$f/_default.json" ; done
  → all four PRESENT at the branch base d38e22b
$ git diff --stat d38e22b..HEAD -- api/sbs_api/agents/fixtures/
  (empty — untouched on this branch)
```

**The audit mischaracterized this in two places.** Its agent table (line 60) says
*"skipped silently when no fixture exists"*, its §Unverified (line 329) says
*"Replay fixtures exist only for the demo complaint `BCO-2026-000001`"*, and line 334
concludes *"no replay fixture matched the audited complaints, so it was skipped at
runtime"*. E3.14 quotes the `except ReplayFixtureMissing` branch as if it described
runtime behaviour. For these four agents that branch is **unreachable**, so the
inference is unsound. The correlator did not run during the audit for the reason the
audit itself found elsewhere — P0-3, the chain had no call site on the ingestion path
— not for want of a fixture.

**Nuance both fix reports omit.** The default fixture is deliberately degenerate, so
"succeeding" is not the same as producing content. Same agent, two complaints:

```
BCO-2026-000001 (complaint-specific fixture)   correlation_strength=0.74  anomaly_flag=true   5 cross_source_signals
BCO-2026-462222 (_default.json fallback)       correlation_strength=0.0   anomaly_flag=false  0 cross_source_signals
```

F8's *"the chain now runs to depth on a real Tier-1 complaint"* is true as to depth
and false as to substance for the correlator: on any non-demo complaint it emits
empty signals and zero correlation. Since the correlator feeds the cockpit strip and
the approval bundle, a demo on any complaint other than `BCO-2026-000001` shows an
empty cross-source panel.

### 6.2 F10's self-reported `MockProvider` cursor defect — **CONFIRMED, reproduced**

Three signed Tier-1 submissions, same API process, nothing written that could trip
the reloader:

```
$ python two_tier1.py 3
BCO-2026-862299: HTTP 201
BCO-2026-862300: HTTP 201
BCO-2026-862301: HTTP 201

  complaint_id   | agent_name | status  | model_provider | n_tools | label | conf | route_to
-----------------+------------+---------+----------------+---------+-------+------+-----------
 BCO-2026-862299 | triage     | success | mock           |       0 | other | 0.55 | info-only
 BCO-2026-862300 | triage     | success | mock           |       0 | other | 0.55 | info-only
 BCO-2026-862301 | triage     | success | mock           |       0 | other | 0.55 | info-only
```

Zero tool calls, `other @ 0.55`, `info-only`, and **no investigation / synthesis /
correlator runs at all** — the chain collapses to one hollow triage row. F10's
description is accurate and its severity assessment is right.

**One thing F10 does not surface, and a handover reader needs it: `run-api.sh`
defaults `SBS_API_RELOAD=true`, and the reloader watches the whole repo root.** That
is why healthy-looking traces keep appearing. In this very run:

```
$ grep -nE "Reloading|Started server process|app_started" api-8443.log
5:    [info] app_started …                                    # 15:26:18
1235: WARNING: WatchFiles detected changes in 'standards-pack/sdk-helpers/python/sbs_webhooks.py',
      'standards-pack/…/test_sbs_webhooks.py'. Reloading...    # during `uv run pytest -q`
1243: [info] app_started …                                    # 15:29:25, fresh process
```

My §2 Tier-1 submission at 15:30:22 was the **first complaint in that fresh process**,
which is the only reason it shows the full four-agent chain with 3/4/2/2 tool calls.
The Tier-2 row in the same run — served by the worker container, which has no
reloader and had already processed `stage-h-full`'s row — came back with `n_tools=0`.
Both halves of that table are in §2 above; they are the same defect seen from two
sides.

**Consequence for the gates.** `stage-h-full` passes because it submits exactly one
complaint per tier, and its Tier-1 half is additionally flattered by whatever reload
happened to precede it. F10 identified this blind spot; it is real, and it means the
green Tier-1 trace in both fix reports and in §1 of this report is **not evidence of
steady-state behaviour**.

### 6.3 F9's 27-field claim — **CONFIRMED**

```
$ awk '/^function AnnexTab/,/^  \];/' app/src/components/docs/DocsTabs.tsx | grep -c "{ key: '"
27
$ awk '/^function AnnexTab/,/^  \];/' app/src/components/docs/DocsTabs.tsx | grep -c "EMPRESA"
0
$ grep -o "27 campos[^<\"]*" app/src/components/docs/DocsTabs.tsx
27 campos Anexo 1-A
$ cd app && npx tsc --noEmit ; echo exit=$?
exit=0     (0 lines of output)
```

Heading and table agree at 27; typecheck clean. F9's own caveat — verified at source
+ typecheck level, not in server HTML, because the tab is client-rendered — still
applies and is honest.

### 6.4 Bonus — the Spectral `--quiet` claim — **CONFIRMED**

```
$ spectral lint … --format=json
[]No results with a severity of 'error' found!
$ spectral lint … --format=json --quiet
[]
$ spectral lint … --format=json | python3 -c "import json,sys; json.load(sys.stdin)"
JSONDecodeError: Extra data: line 1 column 3 (char 2)
```

The P0 report's diagnosis of the gate's Spectral step is exactly right, down to the
error message.

---

## Discrepancies against the prior reports — consolidated

| # | Claim | Source | Reality |
|---|---|---|---|
| D1 | "README step 2 run literally, then README step 3 against it" — passing | P0 report, F6 | **False as written.** The transcript adds `SBS_API_PORT=8443`, which README step 2 does not contain. Run literally, step 2 binds `:8000` and step 3 dies with `curl (7)` on `:8443`, exit 7. F6's actual fix (`.env` precedence) is verified working. |
| D2 | Cockpit renders the audited records (used as §3(d) evidence) | audit E4.6; carried forward implicitly | **True only with a second API on `:8000`.** With the single `:8443` API both reports' §Session state describes, `/app/cockpit` returns **HTTP 500** ("fetch failed"). The two-process requirement is documented nowhere. |
| D3 | cross-source-correlator "skipped silently when no fixture exists"; "fixtures exist only for `BCO-2026-000001`" | audit, agent table + §Unverified + E3.14 | **Wrong.** `_default.json` exists for all four agents since `34a939b`, so `ReplayFixtureMissing` is unreachable for them. The correlator's absence during the audit was P0-3 (no call site), not a missing fixture. |
| D4 | "the chain now runs to depth on a real Tier-1 complaint" | P0 report, F8 | **True as to depth, misleading as to content.** On non-demo complaints the correlator returns the degenerate default: `correlation_strength=0.0`, `anomaly_flag=false`, zero signals. |
| D5 | `MockProvider` cursor defect | F10, §Newly discovered | **Confirmed and reproduced.** F10 is right. What F10 omits: `SBS_API_RELOAD=true` silently resets the cursor mid-session, which is why passing traces keep appearing and why gate output is not reproducible. |
| D6 | Everything else measured | P0 + F10 reports | **Reproduced exactly** — all ten gates, the 774/6 test figure, the golden checksum, the banned-pattern grep, zero table-level autogenerate drift, the 4 residual `drop_index` lines, the served contract, Spectral, F9's 27 fields, provider-identity persistence, `enrichment_requests = 0`. |

Nothing in either fix report was found to be fabricated. D1 and D4 are overstatements
of scope; D2 and D3 are gaps in the original audit that the fix reports inherited.

---

## UNVERIFIED

Recorded, not tested, and not claimable at handover:

1. **`on_prem` against a real vLLM.** No vLLM endpoint on this machine. Every model
   call was `MockProvider` (directly, since the worker and API were set to `mock`) or
   `ReplayProvider`. The `on_prem` value has still never been observed from a genuine
   completion, and the fallback-reports-effective-provider claim in F5 is therefore
   verified only by construction, not by observation. Same caveat both prior reports
   carry.
2. **F3 enforcement.** DIValeVale records; it does not gate. I confirmed the
   record-only posture (`INVALID`/`REJECTED`, `enrichment_requests = 0`) but did not
   test what enforcement would do, since enabling it is exactly what F3 declined to do.
3. **Prior reports' negative controls.** F1's `git stash` of `db/models/__init__.py`
   and F10b's commented-out `persona_task` import both require editing tracked files;
   out of bounds for this run. The guards themselves both run and pass inside the 774.
4. **F9 at the rendered-HTML level.** The Annex tab is client-rendered; verified at
   source + typecheck only, as F9 itself states.
5. **The four residual index-level autogenerate entries** in a real maintainer
   workflow — I confirmed they are emitted, not what happens if someone applies them.
6. **`scripts/run_agent_pipeline_on_new.py`** backfill — not re-run.
7. **Keycloak container healthcheck.** `unhealthy`, `FailingStreak: 159`, exit code 1
   with empty output. The realm is functional (`openid-configuration` → 200; ROPC
   through `demo-login` succeeds), so this looks like a probe misconfiguration, but
   the cause was not investigated. A handover reader will see a red container.
8. **The app's production build.** Not attempted — `next build` is known to corrupt
   the live `next dev` on `:3000` via the shared `app/.next`.
9. **Untouched P1s**, all still open exactly as both reports list them: P1-2 (README
   never explains how to start the cockpit or Keycloak — see D2, which makes it worse
   than described), P1-3 (`institution-api-workflow.md` cockpit URL 404s), P1-6
   (root `.env.example` omits `SBS_API_INTERNAL_API_SECRET`), P1-7 (journey routes
   shell out to a hard-coded `./.venv/bin/python`), P1-8 (`app/README.md` "Five
   screens"). ADR 0001 roster drift, `rank_features` constant, and the
   `clasificación inicial '—'` narrative also remain.

---

## Recommendation — **NO-GO**

The engineering in the two fix reports holds up. All ten gates are green from cold,
774 tests pass, the autogenerate trap is genuinely closed, the contract is clean and
byte-identical to what the API serves, and provider identity is persisted and
discriminating. On the evidence, nothing needs re-doing.

What blocks handover is that a recipient following the documentation would not reach a
working system, and the agent layer they did reach would be hollow after the first
complaint. Three blockers, each small:

1. **`MockProvider`'s cursor never resets** (§6.2). In the default `on_prem`-falls-back-to-mock
   posture — the posture on every machine in this engagement — every complaint after
   the first in a process gets one empty triage row and no chain. A vendor demo on the
   second complaint shows nothing. F10's recommended fix (key the cursor by
   `(agent_name, complaint_id)`, as `ReplayProvider` already does) is a few lines.
   Add the second-submission assertion to `stage-h-full` in the same commit, or the
   gate will keep certifying the defect as fixed. **Also turn `SBS_API_RELOAD` off for
   gate runs** — otherwise the reloader keeps papering over the symptom.
2. **The README's three-command path fails at step 3** (§3). Adding `SBS_API_PORT=8443`
   to README step 2 is a one-line change. It has to happen before anyone else runs the
   walk and concludes the auth chain is broken, which it is not.
3. **The cockpit needs a second API on `:8000` and 500s without it** (§2). Either
   document the two processes and their two auth postures, or point
   `SBS_INTERNAL_API_BASE_URL` at the `:8443` instance. Undocumented, and the failure
   mode is a bare HTTP 500 with `fetch failed` — the worst thing to hand a new team.

Two further items should be written down rather than fixed, so nobody re-derives them:
the cross-source-correlator's degenerate output on non-demo complaints (§6.1, D4), and
the correction that its skip-without-a-fixture behaviour never existed for the shipped
agents (D3) — the audit's §Unverified rows 329/334 should be struck.

With those three landed and the two notes written, this is a **GO**. None of them is
more than an afternoon, and none requires re-opening anything the fix reports closed.

---

## Session state

- **Nothing committed, nothing pushed, no tracked file modified.** `git status --short`
  reports only `?? docs/audit/`, unchanged from the start of this run. This report is
  the one file created.
- The autogenerated migration was inspected and **deleted**; `api/migrations/versions/`
  is back to 21 files. **No autogenerated migration was applied, and no migration
  containing a DROP was applied at any point.** `docker compose down` was run **without
  `-v`** — the volume survived and the DB is at `20260810_0001`, as it was before.
- Runtime left in a working state: compose stack up (postgres/redis healthy, worker,
  webhook-listener, keycloak `unhealthy` per §UNVERIFIED item 7); `sbs-worker`
  force-recreated with `SBS_API_AGENTS_PIPELINE_ENABLED=true` and
  `SBS_API_MODEL_PROVIDER=mock`; one mTLS API on `:8443` (pipeline on, mock provider);
  one plain API on `:8000` for the cockpit; `next dev` on `:3000` untouched throughout.
  A plain `docker compose up -d worker` returns the worker to the default-off posture.
- Two stale uvicorns on `:8443` from the F10 session were stopped at the start,
  identified by port. Three short-lived API processes were started and stopped during
  the README walk in §3.
- Scratch scripts for the demo path and the cursor probe live outside the repo, in
  this session's scratchpad; the only artefacts inside the repo are the gitignored
  batch CSVs under `data/batches/`, which the existing gates also produce.
