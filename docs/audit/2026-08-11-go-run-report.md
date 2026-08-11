# GO run — three NO-GO blockers + handover pack

- **Date:** 2026-08-11
- **Branch:** `fix/handover-p0`, from `107d56f`. **Eight commits, nothing pushed.**
- **Input:** [2026-08-11-verification.md](2026-08-11-verification.md) — the
  authoritative state. Item references (B1, D5, §6.2…) are its numbering. The two
  fix reports are history and were not edited.
- **Result:** all three NO-GO blockers closed, all five handover items done —
  nothing dropped. All ten gates green with the reloader off, **775 passed /
  6 skipped**.
- **Recommendation: GO.** Reasons and the residual list at the end.

---

## Gate table — all ten green, reloader off

```
$ for s in stage-a stage-b stage-c stage-d stage-e stage-f \
           stage-g-contract stage-g-full stage-h-contract stage-h-full; do
    bash scripts/smoke-test-batch.sh $s; done

stage-a            exit=0   11 passed, 2 warnings in 5.31s
stage-b            exit=0   7 passed in 3.90s
stage-c            exit=0   7 passed in 4.27s
stage-d            exit=0   27 passed in 4.95s
stage-e            exit=0   8 passed in 0.20s
stage-f            exit=0   25 passed in 0.33s
stage-g-contract   exit=0   85 passed, 2 warnings in 11.19s
stage-g-full       exit=0   85 passed, 2 warnings in 11.21s  live half: PASS
stage-h-contract   exit=0   37 passed in 3.09s
stage-h-full       exit=0   37 passed in 3.12s  live half: PASS
```

```
$ uv run pytest -q
775 passed, 6 skipped, 4 warnings in 77.54s (0:01:17)
```

774 → 775: one new provider test (`test_mock_provider_cursor_is_per_complaint`).

Golden corpus byte-stable, same checksum as every prior report:

```
golden before: 1b2345643469a05993990272826624eddcbd3f63ead4bb19b18f5e0791a0dc81  # pragma: allowlist secret
golden after:  1b2345643469a05993990272826624eddcbd3f63ead4bb19b18f5e0791a0dc81  # pragma: allowlist secret
```

Banned patterns re-checked, since `smoke_stage_h_live.py` was edited:

```
$ grep -nE "MockTransport|TestClient|ASGITransport|dependency_overrides|mock\.patch|unittest\.mock|monkeypatch" \
    scripts/smoke_stage_g_live.py scripts/smoke_stage_h_live.py
grep exit=1        # 1 = no hits
```

**The API served the entire run in one process** — the point of the reload
change, and the condition `stage-h-full` now depends on:

```
$ grep -c "Reloading" api-final.log             → 0
$ grep -c "Started server process" api-final.log → 1
```

The `:8443` API was started with no `SBS_API_RELOAD` flag at all, and no
`Will watch for changes` line appears: off is now the default.

Contract and schema unchanged by this run: `spectral lint --quiet` → `[]`, exit 0;
alembic head still `20260810_0001`; 21 migration files; no migration was written
or applied, and nothing containing a DROP was applied at any point.

---

## Branch log

```
55618b0 fix(compose): probe the realm Keycloak actually serves in its healthcheck
6f9f03a docs(app): replace the stale route map with the one on disk
9874933 fix(app): resolve the shelled-out Python interpreter from an env var
7880de8 docs(adr): record ADR 0001's roster as built, in an addendum
bab670e docs(handover): write down the sharp edges and the audit-trail errata
c6a8c61 docs: document the cockpit bootstrap, both API processes included
7cbb429 docs(readme): give step 2 the port step 3 already requires
c7910c2 fix(agents): key the mock provider's script cursor per complaint
```

Eight commits, one per item. All passed pre-commit hooks; `--no-verify` was not
used. `git status --short` shows only `?? docs/audit/`.

---

## B1 — MockProvider cursor — **DONE**

**Root cause, one level deeper than F10 had it.** F10 said the cursor "is reset
only by an explicit `reset()` nobody calls". It is in fact called — by all four
agents — but every call site is guarded:

```python
provider = provider or get_provider()
if isinstance(provider, ReplayProvider):
    provider.reset()
```

So `ReplayProvider` is reset per run and `MockProvider` never is. That is why the
two providers behaved differently despite both keeping cursors.

**Fix.** `MockProvider._cursors` is keyed on `(agent_name, complaint_id)`, mirroring
`ReplayProvider`. The `get_provider()` process cache is untouched; only the cursor
stops being process-global. Callers passing no `complaint_id` share one cursor
under a sentinel, preserving the old behaviour for complaint-less unit tests.

### Tests asserting the old semantics: there were none

F10 expected several. There are none — every existing test uses a single complaint
per provider instance, so the change is transparent to all of them. Rather than
manufacture edits, this is stated with evidence: the full suite passed unmodified
except for the one test added, and the new test is the only place carrying the
semantic-change comment.

**Negative control — the new guard actually guards:**

```
$ git stash push -q api/sbs_api/agents/providers/mock.py     # fix out, test in
$ uv run pytest -q tests/test_agent_providers.py
>       assert r.finish_reason == "tool_calls"
E       AssertionError: assert 'stop' == 'tool_calls'
FAILED tests/test_agent_providers.py::test_mock_provider_cursor_is_per_complaint
1 failed, 11 passed in 0.15s
$ git stash pop -q
$ uv run pytest -q tests/test_agent_providers.py
12 passed in 0.14s
```

### `run-api.sh` — reloader off by default

`SBS_API_RELOAD` now defaults to `false`, with the reasoning in the script header
and `SBS_API_RELOAD=true` documented as the development opt-in. Verified above:
zero reloads across a full gate run plus the whole pytest suite, where the old
default reloaded mid-session (verification §6.2 logged exactly that during
`uv run pytest -q`).

### `stage-h-full` hardened

Tier 1 now submits two complaints back to back into the same process; Tier 2
sends a two-row batch through the worker. For **every** complaint on both tiers
the gate asserts a `validation_audit` row ahead of the first `agent_run`, a
non-null `model_provider`, **non-empty `tool_calls`**, and that the chain triage
routed to actually ran. Its precondition fix-command and the `smoke-test-batch.sh`
banner both now carry `SBS_API_RELOAD=false`.

```
[12:18:14] --- Tier 1: two signed POST /v1/complaints, same process ---
[12:18:14] tier 1: 201 Created BCO-2026-465094
[12:18:14] tier 1: 201 Created BCO-2026-465095
[12:18:14] tier1: asserting submission 1/2 (BCO-2026-465094)
[12:18:14] tier1: agent_runs triage(status=success,provider=mock,tools=3), investigation(status=success,provider=mock,tools=4), synthesis(status=success,provider=mock,tools=2), cross-source-correlator(status=success,provider=replay,tools=2)
[12:18:14] tier1: asserting submission 2/2 (BCO-2026-465095)
[12:18:14] tier1: agent_runs triage(status=success,provider=mock,tools=3), investigation(status=success,provider=mock,tools=4), synthesis(status=success,provider=mock,tools=2), cross-source-correlator(status=success,provider=replay,tools=2)
[12:18:14] --- Tier 2: signed POST /v1/batches, 2 rows (worker container) ---
[12:18:15] batch complete: accepted=2
[12:18:16] tier2: asserting row 1/2 (COP-2026-465096)
[12:18:16] tier2: agent_runs triage(...,tools=3), investigation(...,tools=4), synthesis(...,tools=2), cross-source-correlator(...,provider=replay,tools=2)
[12:18:16] tier2: asserting row 2/2 (COP-2026-465097)
[12:18:16] tier2: agent_runs triage(...,tools=3), investigation(...,tools=4), synthesis(...,tools=2), cross-source-correlator(...,provider=replay,tools=2)
[12:18:16] stage-h-full live assertion: PASS
```

Compare the verification's run, where Tier-2 triage came back `tools=0`.

**Negative control — the hardened gate against the old cursor.** Fix stashed,
worker force-recreated, API restarted, gate re-run:

```
[12:01:53] tier1: asserting submission 1/2 (BCO-2026-464113)
[12:01:53] tier1: agent_runs triage(status=success,provider=mock,tools=3), investigation(...), synthesis(...), cross-source-correlator(...)
[12:01:53] tier1: asserting submission 2/2 (BCO-2026-464114)
[12:01:53] FAIL: tier1: triage agent_run for BCO-2026-464114 recorded 0 tool calls
           — the agent produced no work. The model provider's script cursor is
           most likely exhausted; it must be keyed per (agent, complaint).
  live half:     FAIL
FAIL: stage-h-full: contract_rc=0 live_rc=1
```

Submission 1 passes, submission 2 fails, exit 1. The gate could not see this
before and can now.

### The verification's exact probe — three Tier-1 submissions, one process

Proof no reload fired between them:

```
$ grep -c "Reloading" api-b1.log                → 0
$ grep -c "Will watch for changes" api-b1.log   → 0
$ grep -c "Started server process" api-b1.log   → 1
$ grep -c "app_started" api-b1.log              → 1
$ lsof -t -nP -iTCP:8443 -sTCP:LISTEN           → 90740   (unchanged throughout)
```

```
  complaint_id   |       agent_name        | status  | model_provider | n_tools |          label          | conf |   route_to
-----------------+-------------------------+---------+----------------+---------+-------------------------+------+---------------
 BCO-2026-864160 | triage                  | success | mock           |       3 | undisclosed-fees-credit | 0.82 | investigation
 BCO-2026-864160 | investigation           | success | mock           |       4 |                         |      |
 BCO-2026-864160 | synthesis               | success | mock           |       2 |                         |      |
 BCO-2026-864160 | cross-source-correlator | success | replay         |       2 |                         |      |
 BCO-2026-864161 | triage                  | success | mock           |       3 | undisclosed-fees-credit | 0.82 | investigation
 BCO-2026-864161 | investigation           | success | mock           |       4 |                         |      |
 BCO-2026-864161 | synthesis               | success | mock           |       2 |                         |      |
 BCO-2026-864161 | cross-source-correlator | success | replay         |       2 |                         |      |
 BCO-2026-864162 | triage                  | success | mock           |       3 | undisclosed-fees-credit | 0.82 | investigation
 BCO-2026-864162 | investigation           | success | mock           |       4 |                         |      |
 BCO-2026-864162 | synthesis               | success | mock           |       2 |                         |      |
 BCO-2026-864162 | cross-source-correlator | success | replay         |       2 |                         |      |
(12 rows)
```

Against the verification's result for the same probe — `tools=0`, `other`, `0.55`,
`info-only`, no downstream stages on all three.

### Same three-in-a-row through the worker — one Tier-2 batch of 3 rows

The worker is the sharper test: no reloader, and the container demonstrably never
restarted mid-probe.

```
$ docker inspect sbs-worker --format '...'   (before) started=2026-08-11T16:02:11.497783626Z restarts=0 pid=16007
$ docker inspect sbs-worker --format '...'   (after)  started=2026-08-11T16:02:11.497783626Z restarts=0 pid=16007

              batch_id              |  status  | row_count_accepted
------------------------------------+----------+--------------------
 batch_019ff1909a9a74a2b4cd745cf366 | complete |                  3

  complaint_id   |       agent_name        | status  | model_provider | n_tools |          label          |   route_to
-----------------+-------------------------+---------+----------------+---------+-------------------------+---------------
 COP-2026-864213 | triage                  | success | mock           |       3 | undisclosed-fees-credit | investigation
 COP-2026-864213 | investigation           | success | mock           |       4 |                         |
 COP-2026-864213 | synthesis               | success | mock           |       2 |                         |
 COP-2026-864213 | cross-source-correlator | success | replay         |       2 |                         |
 COP-2026-864214 | triage                  | success | mock           |       3 | undisclosed-fees-credit | investigation
 COP-2026-864214 | investigation           | success | mock           |       4 |                         |
 COP-2026-864214 | synthesis               | success | mock           |       2 |                         |
 COP-2026-864214 | cross-source-correlator | success | replay         |       2 |                         |
 COP-2026-864215 | triage                  | success | mock           |       3 | undisclosed-fees-credit | investigation
 COP-2026-864215 | investigation           | success | mock           |       4 |                         |
 COP-2026-864215 | synthesis               | success | mock           |       2 |                         |
 COP-2026-864215 | cross-source-correlator | success | replay         |       2 |                         |
(12 rows)
```

Third complaint identical to the first, in both processes. The defect is closed.

---

## B2 — README step 2 — **DONE**

`SBS_API_PORT=8443` added, with a comment saying why (step 3's hard default and
the dev certs' SANs).

Steps 1–3 run literally as the README now reads, this machine's `.env` present
(`SBS_API_MTLS_MODE=proxy`, the trap), **zero off-README variables exported**:

```
########## STEP 1 ##########
$ bash scripts/dev-up.sh
exit=0
    institutions: SBS-001234 (BANCO_DEMO_001), SBS-005678 (COOPAC_DEMO_002)
    certificate thumbprints loaded (see dev-ca/thumbprints.txt)
    oauth_clients: banco-demo-001 (SBS-001234), coopac-demo-002 (SBS-005678)
==> ready

########## STEP 2 ##########
$ SBS_API_MTLS_MODE=direct \
  SBS_API_AUTH_STUB_ENABLED=false \
  SBS_API_PORT=8443 \
    bash scripts/run-api.sh
==> mTLS direct mode: uvicorn will require client certs signed by dev-ca/ca.pem
[info] app_started  api_version=0.1.0 auth_stub_enabled=False environment=dev

########## STEP 3 ##########
$ bash scripts/smoke-test-auth.sh
exit=0
  mTLS handshake + liveness OK
  cnf.x5t#S256 binding OK
  201 Created OK
  SIGNATURE_REPLAYED OK
  429 + 4 rate-limit headers OK
All auth-chain smoke-test assertions passed.
```

D1 closed. F6's `.env`-precedence fix is confirmed still working: `.env` says
`proxy`, the caller said `direct`, and `direct` won.

---

## B3 — Cockpit bootstrap documented — **DONE**

README gains "Run the supervisor cockpit": the two API processes in a table with
their two auth postures and what each serves, an explicit warning that running
only `:8443` yields HTTP 500 `fetch failed`, Keycloak, `app/.env.local` from
`app/.env.example`, the shared secret's **two different variable names** on the
two sides, `npm install && npm run dev`, the demo-login URL, and the correct
cockpit URL. Linked from the Documentation index.

Also: `docs/demo/institution-api-workflow.md` pointed at `/supervisor` in three
places (lines 124, 162, 304 — the brief named 162; all three were the same
defect). All now `/app/cockpit`, and its cockpit step cross-references the README
rather than implying `npm run dev` suffices. Root `.env.example` gains
`SBS_API_INTERNAL_API_SECRET` with the cross-reference `app/.env.example` already
carried.

**Verified by walking only the new section, from both API processes dead:**

```
$ 8443=0 8000=0                                    (both killed first)
$ bash scripts/dev-up.sh                           exit=0
$ docker compose up -d keycloak                    Container sbs-keycloak Running
$ ...run-api.sh (:8443)   → https://0.0.0.0:8443
$ SBS_API_PORT=8000 bash scripts/run-api.sh → http://0.0.0.0:8000
$ root .env  SBS_API_INTERNAL_API_SECRET=a9b9…<redacted:internal-api-secret>
  app/.env.local SBS_INTERNAL_API_SECRET=a9b9…<redacted:internal-api-secret>   (values match)

$ (one signed Tier-1 complaint through :8443)      BCO-2026-864457: HTTP 201
$ curl .../app/api/auth/demo-login                 307 → /app/cockpit
$ curl .../app/cockpit                             http=200 bytes=88878
  grep -c BCO-2026-864457                          1

       agent_name        | status  | model_provider | n_tools
-------------------------+---------+----------------+---------
 triage                  | success | mock           |       3
 investigation           | success | mock           |       4
 synthesis               | success | mock           |       2
 cross-source-correlator | success | replay         |       2
```

Cold to a cockpit page rendering a record submitted seconds earlier. D2 closed.

---

## K1 — Handover notes + errata — **DONE**

New `docs/HANDOVER-NOTES.md`, linked first in the README's Documentation index.
Covers every write-down the brief listed: the mock/replay posture and that
`on_prem` has never met a real vLLM; NULL `model_provider` on rows predating
`20260810_0001` and why there is no backfill; the correlator's blank
`_default.json` fallback with a fixture comparison table and the pointer to
`BCO-2026-000001`; the read-only worker mount and its force-recreate command; the
worker's pipeline defaulting off; `SBS_API_RELOAD` now defaulting off; the
`demo-login` `0.0.0.0` redirect; the four spurious `drop_index` lines; DIValeVale's
record-only posture with its two prerequisites stated concretely; and the
remaining scaffolds (`rank_features`, the `clasificación inicial '—'` narrative,
`reclamito`/`lupaman`/`insight-chatbot`).

**`scripts/demo.sh` bypassing the HTTP API — verified before writing it down.**
`scripts/demo_replay.py` inserts the `batches` row with `asyncpg` and enqueues
`process_batch` on arq Redis:

```
$ grep -nE "httpx|requests|/v1/|asyncpg|arq|enqueue_job" scripts/demo_replay.py
10:3. Enqueues ``process_batch`` onto the live arq Redis pool.
38:import asyncpg
39:from arq.connections import RedisSettings, create_pool
93:            INSERT INTO batches (
183:        await pool.enqueue_job("process_batch", batch_id)
```

No HTTP client, no `/v1/` path: it exercises the worker, batch pipeline and signed
outbound webhook, but no mTLS, OAuth, HMAC, idempotency or rate limiting. The
notes say so, and point at what does. They also flag that `demo.sh`'s inline
comment about the worker never running agents is stale in the same way
`run_agent_pipeline_on_new.py`'s docstring was — recorded rather than edited, to
keep this commit scoped.

**Errata subsection**, pointing at the verification report, correcting the audit's
correlator fixture claims (D3) and the P0 report's F6/F8 scope overstatements
(D1/D4), and noting F10's cursor diagnosis was right while its test-breakage
prediction was not. **Closed reports were not edited.**

**Documented demo path checked for `BCO-2026-000001`.** Nothing in the docs
promises a populated cross-source panel on a non-golden complaint, so no
correction was needed. What was missing was the positive statement, so the demo
walkthrough — where someone running a demo will actually be looking — now says a
freshly submitted complaint renders an **empty** cross-source panel and that
`BCO-2026-000001` (seeded by `dev-seed.sql`) is the one to use.

---

## K2 — ADR 0001 roster — **DONE**

One appended `## Addendum (2026-08-11) — the roster as built`. No renumbering, no
rewriting, status stays Accepted, the original Decision text untouched. Records:
`triage`/`investigation`/`synthesis` real; `live-ingestion-orchestrator`;
`cross-source-correlator` replay-driven and blank off the golden complaint;
`divalevale` wired record-only; `reclamito`/`lupaman`/`insight-chatbot`
registry-only.

Two facts checked rather than copied from the brief: **`taxonomy-harmonizer`, one
of the five agents the ADR names, no longer exists** — removed with its fixtures,
and `tests/cleanup/test_no_scaffold_agents.py` keeps it gone. And `AGENT_REGISTRY`
is a *display* roster: it holds `divalevale`, `reclamito`, `lupaman`, `triage`,
`investigation`, `insight-chatbot` — so `synthesis` and `cross-source-correlator`
run without appearing on a card. Both are now in the addendum.

---

## K3 — Journey routes' hard-coded interpreter — **DONE**

Six call sites, not the four journey routes alone: `journey/stats`,
`journey/insights`, `journey/recent`, `journey/submit`, `demo/assistant`, and
`lib/sandbox-runner.ts` all hard-coded `path.join(REPO_ROOT, '.venv', 'bin', 'python')`.
All six now call `pythonBin()` from the new `app/src/lib/python.ts`:
`SBS_PYTHON_BIN` when set and non-empty, else the previous path. Whitespace-only is
treated as unset. Read at call time, not module load. Documented in
`app/.env.example`. Additive — an existing checkout resolves to exactly the old path.

```
$ cd app && npx tsc --noEmit        exit=0  (0 lines)
$ npx eslint <the 7 touched files>  exit=0
$ grep -rn "'.venv'" app/src        → only the fallback constant in lib/python.ts
```

**Nothing moved, and the routes still return live data** (running dev server,
fallback path, fresh Keycloak session):

```
  /app/api/journey/stats     http=200 {"hourly_24h":[{"hour":"14:00","count":7},{"hour":"15:00","count":11},…
  /app/api/journey/recent    http=200 {"items":[{"complaint_id":"BCO-2026-864457","institution_id":"SBS-001234",…
  /app/api/journey/insights  http=200 {"kpis":{"complaints_24h":58,"complaints_7d":58,"active_institutions":2,…
```

`recent` lists `BCO-2026-864457` — the complaint submitted during B3's walk.

The env-var branch was exercised against the **shipped module** rather than by
restarting `next dev` on `:3000`, which was left alone as instructed:

```
A) unset                → $REPO_ROOT/.venv/bin/python   === DEFAULT_PYTHON_BIN: true
B) = the same path      → $REPO_ROOT/.venv/bin/python   === DEFAULT_PYTHON_BIN: true
C) = /usr/bin/python3   → /usr/bin/python3              === DEFAULT_PYTHON_BIN: false
D) = "   "              → $REPO_ROOT/.venv/bin/python   (whitespace-only ignored)
```

(First attempt at this compiled the module with an ad-hoc `tsc` call that dropped
the project's `esModuleInterop`, producing broken JS and a `TypeError`. The fault
was in the harness, not the module; re-emitted with the flag, above.)

---

## K4 — `app/README.md` — **DONE**

Rewritten. It claimed "Five screens" against 28 page routes and 31 BFF handlers,
and its layout tree predated the `(supervisor)` route group. Now: the three
audiences, every page route with whether its data is live / server-rendered /
client-fetched / static, the BFF handler groups, the real directory tree, and the
route-group note — the parentheses in `src/app/(supervisor)/` are a Next.js
grouping convention, not a URL segment, **which is why `/supervisor` 404s**. Plus
pointers to the cockpit bootstrap and handover notes, and a warning that
`npm run build` clobbers a running dev server through the shared `.next`.

All 27 enumerated page routes were checked against disk (`all 27 claimed page
routes exist on disk`; 28 `page.tsx` total, the 28th being the `/app/` redirect,
which is listed). The root redirect's behaviour was read off `page.tsx` — it is
no-session → `/app/login`, else the role-based landing route per ADR 0042 D1 —
not the "redirects to /app/cockpit" the old README implied.

---

## K5 — Keycloak healthcheck — **DONE**

**Diagnosed before changing anything**, by running both candidate probes inside
the container:

```
$ docker exec sbs-keycloak bash -c "…/dev/tcp/localhost/8080 … GET /health/ready…"
HTTP/1.0 404 Not Found
{"error":"Unable to find matching target resource method",…}

$ docker exec sbs-keycloak bash -c "…/dev/tcp/localhost/9000 … GET /health/ready…"
HTTP/1.0 200 OK
{ "status": "UP", "checks": [ ] }
```

The probe asked 8080 for `/health/ready`. Keycloak 25 serves health on the 9000
management port **even under `start-dev`** — directly contradicting the comment
sitting above the probe — so it 404'd forever (`FailingStreak: 159` at the start
of this run) while the service worked perfectly.

Fixed by probing the **realm's discovery document** rather than by correcting the
port: `/health/ready` only reports that the server booted, whereas everything
depending on Keycloak here needs the `sbs-demo` realm imported and serving, which
is later and strictly stronger. `echo -e` also became `printf`.

```
$ docker compose config --quiet                      compose config valid
$ docker compose up -d --force-recreate keycloak
  t+5s: starting   t+10s: starting   t+15s: healthy

SERVICE            STATE     STATUS
keycloak           running   Up 10 seconds (healthy)
postgres           running   Up 51 minutes (healthy)
redis              running   Up 51 minutes (healthy)
webhook-listener   running   Up 51 minutes
worker             running   Up 13 minutes

$ docker inspect sbs-keycloak --format '…'    healthy failingStreak=0
$ curl …/realms/sbs-demo/.well-known/openid-configuration   http=200
$ curl …/app/api/auth/demo-login    307 → /app/cockpit   (not ?error=demo_login_failed)
$ curl …/app/cockpit                http=200
```

Healthy, realm still serving, and the session path still obtains real ROPC tokens.

---

## Still open after this run

Nothing from the brief was dropped. What remains is what was already flagged as
out of scope, now all written down in `docs/HANDOVER-NOTES.md`:

1. **`on_prem` has never run against a real vLLM.** Unchanged and unchangeable
   here — no endpoint exists in this environment. The first person with one
   should expect integration work no test on this branch could have caught.
2. **DIValeVale is record-only.** Needs an authoritative
   `institution_id → institution_code` mapping and an ADR 0026 decision on
   `amount_claimed` / `currency`. Both prerequisites are stated concretely in the
   notes.
3. **Four index-level autogenerate entries.** Autogenerate cannot drop a table;
   it still emits four spurious `op.drop_index` lines, so generated migrations
   must be read before use. Closing it means declaring `Index(...)` on four models
   or renaming indexes across shipped migrations.
4. **The correlator returns a blank result off `BCO-2026-000001`.** By design
   (scaffolded agent, blank default fixture) and now documented in three places.
   Adding a per-complaint fixture is how you populate a second one.
5. **Scaffolds:** `rank_features` returns a constant; the investigation narrative
   renders `clasificación inicial '—'` when a classification is absent;
   `reclamito` / `lupaman` / `insight-chatbot` have no runtime.
6. **`scripts/demo.sh`'s inline comment** about the worker never running agents is
   stale. Noted in the handover notes rather than edited, to keep commits scoped
   to their items.

---

## Recommendation — **GO**

All three NO-GO blockers from
[2026-08-11-verification.md](2026-08-11-verification.md) are closed, each with a
negative control rather than only a passing run:

- **B1** — the agent layer no longer hollows out after the first complaint per
  process, proven three-in-a-row on both the API and the worker with the process
  identity pinned; and the gate that certified the defect as fixed now fails
  against it.
- **B2** — the README's three-command path works run literally, `.env` present,
  no off-README variables.
- **B3** — the cockpit bootstrap is documented, including the two API processes
  and the 500 you get without the second, verified cold to a rendered record.

The handover pack (K1–K5) is complete, so a recipient now has: a one-page notes
file for the sharp edges, errata against the closed reports, an ADR whose roster
matches the code, an app README whose route map matches disk, no hard-coded
interpreter path, and a Keycloak container that reports its real state.

Residual items are all either genuinely blocked on something outside this repo
(a vLLM endpoint, an ADR 0026 decision) or documented limitations of deliberately
scaffolded surfaces. None of them makes the system misrepresent itself to someone
following the documentation, which was the actual objection last time.

---

## Session state

- **Eight commits, nothing pushed.** `git status --short` shows only
  `?? docs/audit/`. All hooks passed; `--no-verify` was not used. The three
  closed reports under `docs/audit/` were not edited.
- **No migration was written or applied.** Alembic head is still
  `20260810_0001`, 21 files in `api/migrations/versions/`. Nothing containing a
  DROP was applied at any point. No `docker compose down` was run at all this
  session, with or without `-v`.
- Took ownership of the two API processes as instructed: both were stopped and
  restarted several times (B1 negative control, B2's literal walk, B3's cold
  walk). Final state: one mTLS API on `:8443` (pipeline on, mock provider,
  reloader off by default) and one plain API on `:8000` for the cockpit.
- Compose and `next dev` on `:3000` left alone, except the two changes an item
  required: `sbs-worker` force-recreated (it mounts the repo read-only, so it
  cannot see the B1 fix otherwise) and `sbs-keycloak` force-recreated for K5.
  All five services up; keycloak now reports **healthy**.
- Two negative controls used `git stash push` on
  `api/sbs_api/agents/providers/mock.py` and popped it; the file is restored
  exactly, and `git log`/`git status` above confirm a clean tree.
- Scratch scripts (the Tier-1 probe, the three-row batch submitter) live outside
  the repo in this session's scratchpad. The only in-repo artefacts are the
  gitignored batch CSVs under `data/batches/`, which the gates also produce.
