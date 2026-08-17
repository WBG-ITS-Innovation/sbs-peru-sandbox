# Final check — targeted re-verification of the GO run

- **Date:** 2026-08-11
- **Branch:** `fix/handover-p0` @ `55618b0`. **Nothing committed, nothing pushed,
  no tracked file modified.** No `git stash`, no migration written or applied,
  no `docker compose down -v`.
- **Input treated as hypotheses:**
  [2026-08-11-go-run-report.md](2026-08-11-go-run-report.md). The four earlier
  reports are history and were not read for verdicts, only for the checksum
  recipe. No closed report was edited.
- **Result: GO**, with two documentation findings recorded below — one of them a
  real defect in the artefact K4 produced.

The cursor probe, the cold Keycloak start, the ten gates, the full suite, both
documentation walks and all five spot-checks reproduce. The one thing that did
**not** reproduce as presented is the GO report's own framing of how its gate
table and its B3 transcript were produced; see finding **F2**.

---

## 1. Cold rebuild, then gates

### `docker compose down` (no `-v`) → `docker compose up -d`

```
$ docker compose down
  ... 5 containers stopped and removed, network removed
exit=0

$ docker volume ls --filter name=sbs-suptech-prototype
sbs-suptech-prototype_sbs_keycloak_data
sbs-suptech-prototype_sbs_postgres_data
sbs-suptech-prototype_sbs_redis_data
sbs-suptech-prototype_sbs_webhook_listener_venv
sbs-suptech-prototype_sbs_worker_venv        # all five survive, as intended

$ docker compose up -d
  ... keycloak / redis / postgres / webhook-listener created and started,
      worker started after postgres+redis reported Healthy
exit=0
```

Data survived the teardown — `alembic_version = 20260810_0001`, three
institutions seeded, `BCO-2026-000001` still present.

### Keycloak reaches `healthy` from a genuine cold start under the K5 probe

The GO run only force-recreated a warm container. This is the container's own
health log, which is stronger than polling because it timestamps every probe:

```
$ docker inspect sbs-keycloak --format 'StartedAt={{.State.StartedAt}} Restarts={{.RestartCount}}'
StartedAt=2026-08-11T17:00:37.150614637Z Restarts=0

$ docker inspect sbs-keycloak --format '{{json .State.Health}}'
  probe 1  17:00:42.25  exit=1  "/dev/tcp/localhost/8080: Connection refused"   (server not up yet)
  probe 2  17:00:47.28  exit=0
  probe 3  17:00:52.41  exit=0
  probe 4  17:00:57.46  exit=0
Status: healthy   FailingStreak: 0
```

**Healthy 10.1 s after container start, from cold, on the second probe.** The
single failure is the pre-boot connection refusal inside the 30 s
`start_period`, so it never marked the container unhealthy. Contrast the old
probe's `FailingStreak: 159` recorded at the start of the GO run.

The realm the probe asserts is genuinely served, from the host:

```
$ curl -s -o /dev/null -w 'http=%{http_code}' \
    http://localhost:8081/realms/sbs-demo/.well-known/openid-configuration
http=200
issuer         = http://localhost:8081/realms/sbs-demo
token_endpoint = http://localhost:8081/realms/sbs-demo/protocol/openid-connect/token
```

```
SERVICE            STATE     STATUS
keycloak           running   Up 34 seconds (healthy)
postgres           running   Up 34 seconds (healthy)
redis              running   Up 34 seconds (healthy)
webhook-listener   running   Up 34 seconds
worker             running   Up 32 seconds
```

### Worker recreated per HANDOVER-NOTES

```
$ SBS_API_AGENTS_PIPELINE_ENABLED=true SBS_API_MODEL_PROVIDER=mock \
    docker compose up -d --force-recreate worker
exit=0
StartedAt=2026-08-11T17:01:24.409188506Z Restarts=0 Pid=2083

$ docker exec sbs-worker printenv SBS_API_AGENTS_PIPELINE_ENABLED SBS_API_MODEL_PROVIDER
true
mock
```

### Gate table — all ten green

Run against one `:8443` process started with the precondition
`scripts/smoke_stage_h_live.py` documents in its own docstring
(README step 2 **plus** `SBS_API_AGENTS_PIPELINE_ENABLED=true`; no
`SBS_API_RELOAD` flag at all). See **F2** for why that distinction matters and
what happened when I ran the gates against README step 2 verbatim first.

```
$ for s in stage-a stage-b stage-c stage-d stage-e stage-f \
           stage-g-contract stage-g-full stage-h-contract stage-h-full; do
    bash scripts/smoke-test-batch.sh $s; done

stage-a            exit=0   11 passed, 2 warnings in 5.54s
stage-b            exit=0   7 passed in 4.09s
stage-c            exit=0   7 passed in 4.27s
stage-d            exit=0   27 passed in 5.06s
stage-e            exit=0   8 passed in 0.18s
stage-f            exit=0   25 passed in 0.34s
stage-g-contract   exit=0   85 passed, 2 warnings in 11.89s
stage-g-full       exit=0   85 passed, 2 warnings in 12.48s  live half: PASS
stage-h-contract   exit=0   37 passed in 3.19s
stage-h-full       exit=0   37 passed in 2.99s  live half: PASS
```

```
$ uv run pytest -q
775 passed, 6 skipped, 4 warnings in 78.61s (0:01:18)
```

`stage-h-full`'s live half, verbatim — four rows, four agents each, non-empty
tool calls throughout:

```
[13:07:00] worker has the agent pipeline enabled
[13:07:00] API reachable over mTLS at https://sbs-suptech-sandbox.local:8443
[13:07:00] --- Tier 1: two signed POST /v1/complaints, same process ---
[13:07:00] tier 1: 201 Created BCO-2026-468020
[13:07:00] tier 1: 201 Created BCO-2026-468021
[13:07:00] tier1: agent_runs triage(status=success,provider=mock,tools=3), investigation(...,tools=4), synthesis(...,tools=2), cross-source-correlator(provider=replay,tools=2)
[13:07:01] tier1: agent_runs triage(status=success,provider=mock,tools=3), investigation(...,tools=4), synthesis(...,tools=2), cross-source-correlator(provider=replay,tools=2)
[13:07:01] --- Tier 2: signed POST /v1/batches, 2 rows (worker container) ---
[13:07:02] batch complete: accepted=2
[13:07:02] tier2: agent_runs triage(status=success,provider=mock,tools=3), ... (row 1/2)
[13:07:02] tier2: agent_runs triage(status=success,provider=mock,tools=3), ... (row 2/2)
[13:07:02] stage-h-full live assertion: PASS
```

### One process, zero reloads, across the whole run

The same log covers all ten gates, the full pytest suite, and the cursor probe:

```
$ grep -c "Reloading"              api-final.log → 0
$ grep -c "Will watch for changes" api-final.log → 0
$ grep -c "Started server process" api-final.log → 1
$ grep -c "app_started"            api-final.log → 1
$ grep -c "Shutting down"          api-final.log → 0
$ lsof -t -nP -iTCP:8443 -sTCP:LISTEN → 34389   (identical at start, mid-gates,
                                                 after pytest, after the probe)
```

No `SBS_API_RELOAD` was passed. Reload-off is the default, confirmed
independently in the README-step-2 run as well (`Reloading: 0`,
`Started server process: 1`).

---

## 2. The cursor probe — **PASS**

Three signed Tier-1 submissions into one API process, then one Tier-2 batch of
three rows through the worker container. Process identity pinned on both sides.

```
=== API pid before:      34389
=== worker before:       started=2026-08-11T17:01:24.409188506Z restarts=0 pid=2083

--- Tier 1: three signed POST /v1/complaints, same process ---
[13:09:44] tier 1: 201 Created BCO-2026-771001
[13:09:45] tier 1: 201 Created BCO-2026-771002
[13:09:45] tier 1: 201 Created BCO-2026-771003
=== API pid after tier1: 34389

--- Tier 2: signed POST /v1/batches, 3 rows (worker container) ---
[13:09:45] tier 2: 202 Accepted batch_019ff1cd34be7e839f2045166f93 (3 row)
[13:09:46] batch complete: accepted=3

=== worker after:        started=2026-08-11T17:01:24.409188506Z restarts=0 pid=2083
=== API pid after:       34389
```

Worker `StartedAt`, `Pid` and `RestartCount` are byte-identical before and
after; the container demonstrably did not restart mid-probe. The API PID never
moved, and the log above shows zero reloads over the same window.

```
batch status=complete accepted=3

  complaint_id   |       agent_name        | status  | model_provider | n_tools |          label          | conf |   route_to
-----------------+-------------------------+---------+----------------+---------+-------------------------+------+---------------
 BCO-2026-771001 | triage                  | success | mock           |       3 | undisclosed-fees-credit | 0.82 | investigation
 BCO-2026-771001 | investigation           | success | mock           |       4 |                         |      |
 BCO-2026-771001 | synthesis               | success | mock           |       2 |                         |      |
 BCO-2026-771001 | cross-source-correlator | success | replay         |       2 |                         |      |
 BCO-2026-771002 | triage                  | success | mock           |       3 | undisclosed-fees-credit | 0.82 | investigation
 BCO-2026-771002 | investigation           | success | mock           |       4 |                         |      |
 BCO-2026-771002 | synthesis               | success | mock           |       2 |                         |      |
 BCO-2026-771002 | cross-source-correlator | success | replay         |       2 |                         |      |
 BCO-2026-771003 | triage                  | success | mock           |       3 | undisclosed-fees-credit | 0.82 | investigation
 BCO-2026-771003 | investigation           | success | mock           |       4 |                         |      |
 BCO-2026-771003 | synthesis               | success | mock           |       2 |                         |      |
 BCO-2026-771003 | cross-source-correlator | success | replay         |       2 |                         |      |
 COP-2026-771004 | triage                  | success | mock           |       3 | undisclosed-fees-credit | 0.82 | investigation
 COP-2026-771004 | investigation           | success | mock           |       4 |                         |      |
 COP-2026-771004 | synthesis               | success | mock           |       2 |                         |      |
 COP-2026-771004 | cross-source-correlator | success | replay         |       2 |                         |      |
 COP-2026-771005 | triage                  | success | mock           |       3 | undisclosed-fees-credit | 0.82 | investigation
 COP-2026-771005 | investigation           | success | mock           |       4 |                         |      |
 COP-2026-771005 | synthesis               | success | mock           |       2 |                         |      |
 COP-2026-771005 | cross-source-correlator | success | replay         |       2 |                         |      |
 COP-2026-771006 | triage                  | success | mock           |       3 | undisclosed-fees-credit | 0.82 | investigation
 COP-2026-771006 | investigation           | success | mock           |       4 |                         |      |
 COP-2026-771006 | synthesis               | success | mock           |       2 |                         |      |
 COP-2026-771006 | cross-source-correlator | success | replay         |       2 |                         |      |
(24 rows)

--- per-complaint verdict (n_tools>0, label!='other', conf!=0.55, full chain) ---
  BCO-2026-771001: OK
  BCO-2026-771002: OK
  BCO-2026-771003: OK
  COP-2026-771004: OK
  COP-2026-771005: OK
  COP-2026-771006: OK

CURSOR PROBE: PASS
```

All six rows satisfy every condition the brief named: `n_tools > 0` on all 24
agent runs, `label = undisclosed-fees-credit` (never `other`),
`confidence = 0.82` (never `0.55`), and the routed chain
`investigation` → `synthesis` → `cross-source-correlator` present for every
complaint. **The first and third Tier-1 complaints are byte-identical in shape**
(`BCO-2026-771001` vs `BCO-2026-771003`: same four agents, same tool counts,
same label, same confidence, same route) — which is the whole point. Same for
the first and third worker rows.

The probe reuses `scripts/smoke_stage_h_live.py`'s signing and submission
helpers unmodified, imported as a module from an out-of-repo scratch script. No
in-process client, no patching; every request is real curl over mTLS.

---

## 3. Documentation walks

### README steps 1–3, literally, zero off-README variables

`.env` present, containing the `SBS_API_MTLS_MODE=proxy` trap.

```
########## STEP 1 ##########
$ bash scripts/dev-up.sh
exit=0
    institutions: SBS-001234 (BANCO_DEMO_001), SBS-005678 (COOPAC_DEMO_002)
    certificate thumbprints loaded (see dev-ca/thumbprints.txt)
    oauth_clients: banco-demo-001 (SBS-001234), coopac-demo-002 (SBS-005678)
==> ready

########## STEP 2 ##########
$ SBS_API_MTLS_MODE=direct SBS_API_AUTH_STUB_ENABLED=false SBS_API_PORT=8443 \
    bash scripts/run-api.sh
==> mTLS direct mode: uvicorn will require client certs signed by dev-ca/ca.pem
[info] app_started  api_version=0.1.0 auth_stub_enabled=False environment=dev
INFO:     Uvicorn running on https://0.0.0.0:8443

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

B2 holds. F6's `.env`-precedence fix still works: `.env` says `proxy`, the
caller said `direct`, `direct` won.

### The cockpit section, from both API processes dead

```
$ 8443=0  8000=0                                    (both killed first)
$ bash scripts/dev-up.sh                            exit=0
$ docker compose up -d keycloak                     Container sbs-keycloak Running
$ SBS_API_MTLS_MODE=direct SBS_API_AUTH_STUB_ENABLED=false SBS_API_PORT=8443 \
    bash scripts/run-api.sh                         → https://0.0.0.0:8443  pid=43160
$ SBS_API_PORT=8000 bash scripts/run-api.sh         → http://0.0.0.0:8000   pid=43161

  root .env       SBS_API_INTERNAL_API_SECRET = a9b9…<redacted:internal-api-secret>
  app/.env.local  SBS_INTERNAL_API_SECRET     = a9b9…<redacted:internal-api-secret>    (values match)

$ (one signed Tier-1 complaint through :8443)       BCO-2026-772001: HTTP 201
$ curl .../app/api/auth/demo-login                  307 → /app/cockpit
$ curl .../app/cockpit  (with the session cookie)   http=200  bytes=89072
  grep -c BCO-2026-772001                           1
```

**Cold to a cockpit page rendering a complaint submitted seconds earlier.** D2
holds.

I also falsified the section's central warning rather than taking it on trust:

```
$ kill :8000;  curl .../app/cockpit  → http=500,  body contains "fetch failed"
$ restart :8000; curl .../app/cockpit → http=200,  bytes=89072
```

The README's "running only `:8443` yields HTTP 500 `fetch failed`" is exactly
right, in both directions.

**One deviation, stated:** section step 4 (`cp app/.env.example app/.env.local`,
then edit) and step 5 (`npm run dev`) were not executed destructively, because
`next dev` on `:3000` was outside the brief's kill list and overwriting
`app/.env.local` would have required restarting it. Instead I produced what
step 4 yields — the example copied, the secret edited to match root `.env` — and
diffed it against the live file:

```
  SBS_INTERNAL_API_BASE_URL    fresh=http://localhost:8000  live=http://localhost:8000  SAME
  SBS_INTERNAL_API_SECRET      fresh=a9b9…<redacted>        live=a9b9…<redacted>        SAME
  SBS_DEMO_MODE                fresh=true                   live=true                   SAME
  keys only in the fresh copy (unset in live, defaulted in code):
    KEYCLOAK_BASE_URL, KEYCLOAK_CLIENT_ID, KEYCLOAK_REALM,
    KEYCLOAK_REDIRECT_URI, KEYCLOAK_POST_LOGOUT_REDIRECT_URI
```

The running server's configuration is a subset of what step 4 produces, on
every variable the walk depends on, so the walk above exercises the documented
configuration. `app/.env.local` was not touched.

### `/supervisor` in the demo walkthrough

```
$ grep -n "/supervisor" docs/demo/institution-api-workflow.md
grep exit=1        # 1 = no hits
```

Zero `/supervisor` path references anywhere in the file. The GO run's claim that
all three (lines 124, 162, 304) are fixed holds. The word "supervisor" still
appears six times as English prose ("the supervisor cockpit shows it"), which is
correct and not what the defect was.

---

## 4. Spot-checks against the live system

### (a) HANDOVER-NOTES' correlator fixture claim — **matches in both directions**

`BCO-2026-771001`, submitted minutes earlier, non-golden:

```json
{ "correlation_strength": 0.0,  "anomaly_flag": false, "composite_score": 0.0,
  "cross_source_signals": [], "channel_contributions": [], "scaffolded": true,
  "reasoning_summary": "Correlator complete." }
```

`BCO-2026-000001`, the golden complaint's stored run:

```json
{ "correlation_strength": 0.74, "anomaly_flag": true, "composite_score": 0.74,
  "cross_source_signals": [ complaints 0.42, social 0.31, indecopi 0.38,
                            plavia 0.29, internal 0.22 ],   // 5 signals
  "reasoning_summary": "Correlator complete: cross-source signal aligned with
                        cockpit anomaly card." }
```

The notes' table reads `0.74 / true / 5` against `0.0 / false / 0`. That is
exactly what the database holds, on both rows. The status is `success` with a
non-null `model_provider` in both cases, as the notes also say.

### (b) ADR 0001 addendum's registry claim — **matches**

```
$ python -c "from sbs_api.agents.registry import AGENT_REGISTRY; print(sorted(AGENT_REGISTRY))"
6 entries: ['divalevale', 'insight-chatbot', 'investigation', 'lupaman',
            'reclamito', 'triage']
```

Exactly the six the addendum names. And in the last hour of live traffic:

```
       agent_name        | count
-------------------------+-------
 cross-source-correlator |    23
 investigation           |    23
 synthesis               |    23
 triage                  |    23
```

`synthesis` and `cross-source-correlator` write `agent_runs` while absent from
the registry — the addendum's "display roster, deliberately not the same set"
wording is accurate.

### (c) HANDOVER-NOTES' `demo-login` `0.0.0.0` redirect — **matches**

```
$ curl -sS -D - -o /dev/null http://localhost:3000/app/api/auth/demo-login
HTTP/1.1 307 Temporary Redirect
location: http://0.0.0.0:3000/app/cockpit
```

Verbatim what the notes warn about, including the scripted-client hazard.

### (d) Three routes from the new `app/README.md` route map — **one route map row confirmed, two found wrong**

| Route | `app/README.md` claims | On disk | Verdict |
|---|---|---|---|
| `/app/cockpit` | Live — server-rendered via `internalGet` | `src/app/(supervisor)/cockpit/page.tsx`, no `'use client'`, 3 `internalGet` calls incl. `/v1/internal/cockpit` | **correct** |
| `/app/rr1` | Static — renders `@/lib/rr1-2025.json` | `src/app/(supervisor)/rr1/page.tsx`, `import rr1 from '@/lib/rr1-2025.json'`, no fetch | **correct** |
| `/app/analytics` | **Live — client fetch** | `src/app/(supervisor)/analytics/page.tsx`, 382 lines, server component, **zero** `fetch(` / `useEffect` / `'use client'` / `internalGet`, all values hard-coded `MATRIX_ROWS` / `TOP_MOTIVOS` / `TOP_PRODUCTS` constants, every button `disabled` | **wrong** |

The third is finding **F1** below. Having found it, I audited the remaining
twelve supervisor rows rather than stopping at three:

| Route | Claim | Reality | |
|---|---|---|---|
| `/app/cockpit/aggregates` | Live — client fetches `/app/api/aggregates/*` | `AggregatesWorkspace` → `AggregateTables`/`RedFlags`/`LiveIngestionBanner`, 8 fetches to `/app/api/aggregates/{patterns,social,trend,sources,feed}` | ok |
| `/app/queue` | **Live — client fetch** | 28-line server component rendering an `EmptyState`; comment reads *"stubbed for the May 25 demo per the drop ladder"*; zero fetches | **wrong** |
| `/app/findings`, `/app/approvals`, `/app/audit` | Live — server-rendered | 2 server-side calls each | ok |
| `/app/processing` | Live — client fetch | `ProcessingListClient` (`'use client'`) → `/app/api/journey/recent` | ok |
| `/app/assistant` | Live — client fetch | `LiveAssistantChat` (`'use client'`) → `/app/api/demo/assistant` | ok |
| `/app/admin` | Live — client fetch | `SandboxAdmin` (`'use client'`) → `/app/api/admin/audit`, `/app/api/aggregates/feed` | ok |
| `/app/sandbox` | Live — client fetch | `SandboxControl` (`'use client'`) → 4 `/app/api/sandbox/*` endpoints | ok |
| `/app/demo-journey` | Mixed — live plus `golden-complaint.json` | `DemoJourneySbs` → `/app/api/journey/{audit,findings}`; page imports the fixture | ok |
| `/app/docs`, `/app/ingestion` | Static | no fetch | ok |

Thirteen of fifteen supervisor rows are right. Two are wrong, both in the same
direction. `/supervisor` correctly does not exist on disk — the only match is
the parenthesised route group `src/app/(supervisor)`, which is the README's own
explanation for the 404.

### (e) `SBS_PYTHON_BIN` — journey routes still return live data on the fallback path

`SBS_PYTHON_BIN` is unset in the running `next dev` process (pid 5795), so all
three routes resolve `DEFAULT_PYTHON_BIN` — the pre-change path.

```
  /app/api/journey/stats     http=200 {"hourly_24h":[{"hour":"14:00","count":7},{"hour":"15:00","count":11},…
  /app/api/journey/recent    http=200 {"items":[{"complaint_id":"COP-2026-771006","institution_id":"SBS-005678",…
  /app/api/journey/insights  http=200 {"kpis":{"complaints_24h":83,"complaints_7d":83,"active_institutions":2,…
```

`recent` returns `COP-2026-771006` — the last row of the cursor probe's Tier-2
batch, submitted through the worker minutes earlier. This is live data reaching
the cockpit through the refactored interpreter resolution, not a cached page.

---

## 5. Branch hygiene

```
$ git status --short
?? docs/audit/

$ git log --oneline oss-release-pr..HEAD | wc -l
21

$ ls api/migrations/versions/*.py | wc -l
21

$ cd api && uv run alembic heads
20260810_0001 (head)

$ docker exec sbs-postgres psql -U sbs -d sbs_dev -tAc "select version_num from alembic_version"
20260810_0001

$ find data/synthetic-corpus-golden -type f | sort | xargs shasum -a 256 | shasum -a 256
before: 1b2345643469a05993990272826624eddcbd3f63ead4bb19b18f5e0791a0dc81  # pragma: allowlist secret
after:  1b2345643469a05993990272826624eddcbd3f63ead4bb19b18f5e0791a0dc81  # pragma: allowlist secret
```

All five clean. The only new path in the tree is this file, under the already
untracked `docs/audit/`.

---

## Findings

### F1 — `app/README.md` misclassifies two page routes as live — **real defect**

`/app/queue` and `/app/analytics` are both listed under **"Live — client
fetch"**. Neither makes any data access whatsoever:

- **`/app/queue`** is a 28-line server component rendering an `EmptyState`, with
  the comment *"Risk Queue — stubbed for the May 25 demo per the drop ladder."*
- **`/app/analytics`** is a 382-line server component whose own header comment
  reads: *"This page is intentionally a preview: all controls show a 'Vista
  previa · no conectado al flujo operativo actual' disclaimer and the buttons
  are disabled. **No backend calls are made from this page; every value is
  illustrative.**"* Every figure in its heat matrix, top-motivos and
  top-products tables is a literal in the source.

This matters because K4 existed precisely to replace a route map that
misrepresented the app, and the GO report's evidence for it —
*"All 27 enumerated page routes were checked against disk"* — verified
**existence**, not **classification**. Both errors run in the same direction:
they promise live data where the page ships hard-coded samples. A reader
following the route map to demo `/app/analytics` will present illustrative
constants as pilot output.

Cheap to fix: two table cells, e.g. `Static — preview, values illustrative, all
controls disabled` and `Static — stub, renders an EmptyState`. The page bodies
already carry the correct description in Spanish in the UI and in English in the
comments; only the README disagrees with them.

### F2 — the GO report does not state the invocation behind its gate table

Started per README step 2 **exactly as written**, the `:8443` API does not carry
`SBS_API_AGENTS_PIPELINE_ENABLED`, which defaults to `False`
(`api/sbs_api/config.py:318`). Nine gates still pass; `stage-h-full` fails:

```
stage-h-full       exit=1   37 passed in 3.07s   live half: FAIL
[13:03:59] tier 1: 201 Created BCO-2026-467839
[13:03:59] tier1: asserting submission 1/2 (BCO-2026-467839)
[13:04:59] FAIL: tier1: no triage agent_run for BCO-2026-467839 within 60s
```

This is **not** a documentation lie: `smoke_stage_h_live.py`'s docstring states
its own precondition, which is README step 2 plus that one variable, and the
README never claims step 2 is a gate harness. But two GO-report transcripts are
under-specified as a result:

1. Its gate table gives no start command, so a reader reasonably assumes the
   README-literal process, under which the table is not reproducible.
2. Its **B3** section presents a walk of "only the new section" and then shows
   four `agent_runs` for `BCO-2026-864457`. Walking that section literally, I
   got the cockpit rendering the complaint at HTTP 200 — and **zero**
   `agent_runs`, necessarily, because the section's `:8443` command is README
   step 2. The B3 conclusion holds; the agent-runs table in it cannot have come
   from the process the section documents.

The fix is one line in whichever document a future runner reads: state that the
gate suite needs `SBS_API_AGENTS_PIPELINE_ENABLED=true` on the `:8443` process.
`HANDOVER-NOTES.md` already says this for the **worker** and not for the API.

### Not a finding, but worth a maintainer's eye

`.env` (untracked, gitignored) carries what looks like a live Azure OpenAI API
key alongside the sandbox secrets. Nothing in this repository reads it, and it
is not committed, but it is a real credential sitting in a working tree that
gets copied around during a handover. Rotate it or move it out.

---

## GO / NO-GO — **GO**

**Reasons to go.**

- **The cursor probe passes decisively** — the single most important check.
  Six complaints across two processes, all 24 agent runs with non-empty tool
  calls, correct label and confidence, the full routed chain on every one, and
  the first and third complaint indistinguishable on both tiers. Process
  identity pinned throughout: one API PID with zero reloads, one worker
  container with an unchanged `StartedAt`, `Pid` and `restarts=0`. B1 is closed
  on evidence that could not be produced by a lucky restart.
- **Everything survives a genuine cold rebuild.** `down` (volumes intact) →
  `up -d` → Keycloak healthy in 10.1 s under the K5 probe with the realm serving
  200 → worker recreated → ten gates green → 775 passed / 6 skipped. The GO run
  only ever recreated a warm Keycloak; this one did it cold and the probe
  behaved better than advertised.
- **Both documentation walks work as written.** README 1–3 literally with the
  `.env` `proxy` trap in place; the cockpit section from both API processes dead
  to a page rendering a complaint submitted seconds earlier — and its 500
  `fetch failed` warning is correct in both directions when tested rather than
  assumed.
- **Four of the five spot-checks match their claims exactly**, including the two
  that are easiest to get subtly wrong: the correlator's populated-vs-blank
  behaviour checked in *both* directions, and the registry's deliberate
  divergence from the set of agents that write `agent_runs`.
- Branch hygiene is clean on all five counts, and no state was mutated: no
  commit, no push, no tracked-file edit, no stash, no migration, no `-v`.

**Why the findings do not block.** F1 is two wrong cells in one Markdown table.
It is a genuine defect in K4's deliverable and it does misrepresent the app to a
reader — but it misrepresents two secondary screens as live when they are
labelled "vista previa · no conectado" and "stubbed" in the UI a demo audience
actually sees, so the app corrects the document at the moment it matters. F2 is
a precision problem in a closed report, not in the system: every gate passes
under the precondition the gate itself documents.

**Do these two before handover** (both are documentation, minutes of work):

1. Reclassify `/app/queue` and `/app/analytics` in `app/README.md` as static.
2. Record that the gate suite needs `SBS_API_AGENTS_PIPELINE_ENABLED=true` on
   the `:8443` API, next to the line in `HANDOVER-NOTES.md` that already says it
   for the worker.

---

## Gate table

```
stage-a            exit=0   11 passed, 2 warnings in 5.54s
stage-b            exit=0   7 passed in 4.09s
stage-c            exit=0   7 passed in 4.27s
stage-d            exit=0   27 passed in 5.06s
stage-e            exit=0   8 passed in 0.18s
stage-f            exit=0   25 passed in 0.34s
stage-g-contract   exit=0   85 passed, 2 warnings in 11.89s
stage-g-full       exit=0   85 passed, 2 warnings in 12.48s  live half: PASS
stage-h-contract   exit=0   37 passed in 3.19s
stage-h-full       exit=0   37 passed in 2.99s  live half: PASS

uv run pytest -q   775 passed, 6 skipped, 4 warnings in 78.61s
```

## Cursor probe — six rows

| Complaint | Tier | n_tools (triage/inv/syn/corr) | label | conf | chain routed | verdict |
|---|---|---|---|---|---|---|
| `BCO-2026-771001` | 1 | 3 / 4 / 2 / 2 | `undisclosed-fees-credit` | 0.82 | investigation → synthesis → correlator | **OK** |
| `BCO-2026-771002` | 1 | 3 / 4 / 2 / 2 | `undisclosed-fees-credit` | 0.82 | investigation → synthesis → correlator | **OK** |
| `BCO-2026-771003` | 1 | 3 / 4 / 2 / 2 | `undisclosed-fees-credit` | 0.82 | investigation → synthesis → correlator | **OK** |
| `COP-2026-771004` | 2 | 3 / 4 / 2 / 2 | `undisclosed-fees-credit` | 0.82 | investigation → synthesis → correlator | **OK** |
| `COP-2026-771005` | 2 | 3 / 4 / 2 / 2 | `undisclosed-fees-credit` | 0.82 | investigation → synthesis → correlator | **OK** |
| `COP-2026-771006` | 2 | 3 / 4 / 2 / 2 | `undisclosed-fees-credit` | 0.82 | investigation → synthesis → correlator | **OK** |

One API PID (34389) and one worker container (pid 2083, `restarts=0`,
unchanged `StartedAt`) served all six. **CURSOR PROBE: PASS.**

**Report path:** `docs/audit/2026-08-11-final-check.md`

---

## Session state

- **No commit, no push, no tracked-file modification.** `git status --short` is
  `?? docs/audit/`, exactly as before this run. No `git stash` at any point.
- **No migration written or applied.** Head `20260810_0001` in both the files
  and the database; 21 migration files. Nothing containing a DROP ran.
- **`docker compose down` was run once, without `-v`.** All five named volumes
  survived and the database came back with its data.
- Both API processes were taken over: killed and restarted four times across the
  gate run, the README-literal walk, and the cockpit walk. **Final state:** one
  mTLS API on `:8443` (pid 43160, README step 2 verbatim) and one plain API on
  `:8000` (pid 43883) for the cockpit. Note that `:8443` currently has the agent
  pipeline **off**, because the cockpit walk started it per README step 2 —
  restart it with `SBS_API_AGENTS_PIPELINE_ENABLED=true` before running the gate
  suite again.
- `next dev` on `:3000` (pid 5795) was left running and untouched;
  `app/.env.local` was not modified. Compose services: all five up, keycloak
  healthy.
- Scratch scripts (the cursor probe, the single-complaint submitter) live
  outside the repo in this session's scratchpad and import
  `scripts/smoke_stage_h_live.py` read-only. The only in-repo artefacts are the
  gitignored batch CSVs under `data/batches/`, which the gates also produce.
