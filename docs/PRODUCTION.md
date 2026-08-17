# Production deployment

For the platform engineer at a bank, a supervisory authority, or any other
institution standing this up outside the SBS sandbox.

This repository is a **production-ready reference implementation — production
deployment requires completing [OPERATOR-CHECKLIST.md](OPERATOR-CHECKLIST.md)**.
That distinction is the whole point of this document. The code paths described
below exist and are exercised by the gate suite; the operational
substrate around them — certificates from a real CA, a secrets manager, tested
backups, a load test at your volume — is yours to provide, and the checklist is
the list.

Read this alongside two neighbours, which it deliberately does not duplicate:

- **[HANDOVER-NOTES.md](HANDOVER-NOTES.md)** — the sharp edges. Every
  operational caveat lives there, not here. If something below says "see the
  handover notes", go read it before you deploy.
- **[DEPLOY.md](DEPLOY.md)** — an explicit scaffold for a Helm/k8s path that
  **has not been written**. Nothing in it has been executed. This document
  covers what the repository actually supports today; DEPLOY.md describes where
  a chart would go when someone writes one.

---

## 1. Reference topology

The system is four runtime processes plus three backing services. The shape
below is what the compose stack runs and what the gates exercise; substitute
managed services for the backing tier as noted in §4.

```
                        ┌──────────────────────────────┐
   supervised           │  Gateway / load balancer     │
   institutions ──mTLS──▶  TLS or mTLS termination     │
                        └───────────┬──────────────────┘
                                    │
              ┌─────────────────────┴───────────────────┐
              │                                         │
   ┌──────────▼──────────┐                  ┌───────────▼──────────┐
   │ Institution-facing  │                  │ Supervisor cockpit   │
   │ API  (FastAPI)      │                  │ (Next.js 15)         │
   │ mTLS + OAuth + HMAC │                  │ Keycloak-backed      │
   │ auth stub OFF       │                  │ session              │
   └──────────┬──────────┘                  └───────────┬──────────┘
              │                                         │ server-side
              │                                         │ fetch, shared
              │                              ┌──────────▼──────────┐
              │                              │ Internal API        │
              │                              │ (FastAPI)           │
              │                              │ bearer secret on    │
              │                              │ /v1/internal/*      │
              └──────────┬───────────────────┴──────────┬──────────┘
                         │                              │
        ┌────────────────▼──────┐   ┌───────────────────▼─────┐
        │ PostgreSQL            │   │ Redis                   │
        │ (system of record)    │   │ (arq queue, idempotency,│
        └───────────────────────┘   │  HMAC replay cache)     │
                                    └───────────┬─────────────┘
                                                │
                                    ┌───────────▼─────────────┐
                                    │ Worker (arq)            │
                                    │ Tier-2 batch pipeline   │
                                    └─────────────────────────┘
                        ┌─────────────────────────────────────┐
                        │ Keycloak — supervisor identity      │
                        └─────────────────────────────────────┘
```

### The two-API posture is not optional

The institution-facing and supervisor-facing channels run as **two separate API
processes from the same image**, because they have deliberately different auth
postures. This is the single most common thing to get wrong.

| Process | Port (sandbox) | Posture | Serves |
|---|---|---|---|
| Institution-facing | `8443` | mTLS, real auth chain, `SBS_API_AUTH_STUB_ENABLED=false` | `POST /v1/complaints`, `POST /v1/batches` — everything an institution calls |
| Internal | `8000` | No mTLS; shared-secret bearer on `/v1/internal/*` | The cockpit's server-side fetches only |

The internal API **must never be reachable from the internet**. Its
authorization on `/v1/internal/*` is a single shared bearer secret
(`SBS_API_INTERNAL_API_SECRET`), which is appropriate for a server-to-server hop
inside a trust boundary and nothing more. Bind it to a private network or a
cluster-internal service; publishing it is equivalent to publishing the
supervisor data set.

Running only the `8443` process leaves the cockpit unable to reach a backend and
`/app/cockpit` returns HTTP 500 with `fetch failed`.

### mTLS termination — two supported modes

`SBS_API_MTLS_MODE` (ADR 0031) selects how the peer certificate reaches the
runtime:

- **`direct`** — uvicorn terminates TLS and the API reads the peer certificate
  from the ASGI scope. Fewest moving parts; the API owns the TLS listener.
- **`proxy`** — a gateway (Envoy, nginx, or an ingress controller) terminates
  and validates the client certificate, then forwards the verified metadata in
  a header. The header name is `SBS_API_PROXY_TRUSTED_XFCC_HEADER`, defaulting
  to `x-forwarded-client-cert` (the Envoy convention). **Choose this mode for
  any deployment with a load balancer in front.**

  In proxy mode the API trusts that header unconditionally. The gateway must
  therefore strip any client-supplied `X-Forwarded-Client-Cert` on ingress, and
  nothing may be able to reach the API except through the gateway. If both are
  not true, any caller can assert any institution's identity.

- **`disabled`** — only valid with the auth stub on. Never production.

`SBS_API_DISABLE_MTLS_FOR_TESTS` is a test-only escape hatch. Production
overlays never set it.

---

## 2. Secrets

**No `.env` file in production.** The `.env` / `.env.local` mechanism is a
developer convenience. In production, inject every value as an environment
variable from your secrets manager (Key Vault, Secrets Manager, Vault, sealed
secrets — whatever your platform standardises on). The application reads plain
environment variables; it neither knows nor cares where they came from.

Configuration is a `pydantic-settings` model at `api/sbs_api/config.py` with the
env prefix **`SBS_API_`**. Two exceptions carry no prefix so they stay the
credential block WBG ITS already issues: the `AZURE_OPENAI_*` variables.

### Secret vs. configuration

Treat this split as authoritative — it comes from the settings model, not from
the `.env.example` comments.

**Secret — must come from the secrets manager, must be rotatable, must never be
logged or committed:**

| Variable | What it protects |
|---|---|
| `SBS_API_DATABASE_URL` | Contains the Postgres password |
| `SBS_API_REDIS_URL` | Contains the Redis password, if set |
| `SBS_API_INTERNAL_API_SECRET` | The only thing standing in front of `/v1/internal/*` |
| `AZURE_OPENAI_API_KEY` | Cloud model credential — only if you run the `cloud` provider |
| Per-institution HMAC secrets | Stored in the database, not in env; rotation grace is `SBS_API_HMAC_SECRET_ROTATION_GRACE_SECONDS` |
| Keycloak client secret, admin credentials | See §3 |
| TLS server key, client-CA trust bundle | Filesystem or mounted secret, never in the image |

`SBS_API_INTERNAL_API_SECRET` must match the cockpit's `SBS_INTERNAL_API_SECRET`
exactly. They are the same secret named twice — one for each side of the hop.

**Configuration — non-secret, safe in a ConfigMap, values file, or Helm chart:**

`SBS_API_ENVIRONMENT` (set it to `prod`), `SBS_API_MTLS_MODE`,
`SBS_API_PROXY_TRUSTED_XFCC_HEADER`, `SBS_API_AUTH_STUB_ENABLED` (must be
`false`), `SBS_API_LOG_FORMAT` (set `json`), `SBS_API_LOG_LEVEL`,
`SBS_API_OTEL_*`, `SBS_API_DB_POOL_SIZE`, `SBS_API_DB_POOL_MAX_OVERFLOW`,
`SBS_API_MAX_REQUEST_BODY_BYTES`, `SBS_API_MAX_BATCH_FILE_BYTES`,
`SBS_API_BATCH_STORAGE_PATH`, `SBS_API_BATCH_STORAGE_PRUNE_DAYS`,
`SBS_API_IDEMPOTENCY_*`, `SBS_API_HMAC_TIMESTAMP_SKEW_SECONDS`,
`SBS_API_HMAC_REPLAY_CACHE_TTL_SECONDS`, `SBS_API_RATE_LIMIT_*`,
`SBS_API_WEBHOOK_REQUEST_TIMEOUT_SECONDS`, `SBS_API_CORS_ALLOW_ORIGINS`,
`SBS_API_AGENTS_PIPELINE_ENABLED`, `SBS_API_MODEL_PROVIDER`,
`SBS_API_READINESS_*`, `SBS_API_BUILD_SHA`.

### Settings that must change from their defaults before go-live

| Setting | Default | Production value |
|---|---|---|
| `SBS_API_ENVIRONMENT` | `dev` | `prod` |
| `SBS_API_AUTH_STUB_ENABLED` | varies by process | `false` on the institution-facing process |
| `SBS_API_MTLS_MODE` | `disabled` | `direct` or `proxy` |
| `SBS_API_LOG_FORMAT` | `console` | `json` |
| `SBS_API_OTEL_TRACES_EXPORTER` | `console` | `otlp` |
| `SBS_API_ALLOW_INSECURE_WEBHOOK_URLS` | `false` | leave `false` |
| `SBS_API_DISABLE_MTLS_FOR_TESTS` | `false` | leave `false` |
| `SBS_API_CORS_ALLOW_ORIGINS` | permissive for dev | your cockpit origin only |
| `SBS_DEMO_MODE` (cockpit) | `true` in the sandbox | `false` — see §3 |

---

## 3. Keycloak

The supervisor session is Keycloak-backed (ADR 0040).

**Do not run the sandbox's Keycloak configuration in production.** The compose
service runs `start-dev --import-realm` with `KC_DB: dev-file` (in-memory H2
with on-disk persistence) and a bootstrap admin of `admin`/`admin`. All three
are sandbox-only.

For production:

- Run Keycloak in **production mode** (`start`, not `start-dev`). Production
  mode requires an explicit hostname and enforces HTTPS; `KC_HOSTNAME_STRICT`
  must not be `false`.
- Back it with **PostgreSQL**, not `dev-file`. A `dev-file` Keycloak loses its
  state with the container.
- Rotate the bootstrap admin immediately and manage it as a secret.

**Realm import strategy.** The sandbox realm at `infra/keycloak/` is imported
automatically by `--import-realm` on every start. That is right for a
disposable demo and wrong for production, where the realm holds real operator
identities: an import on boot competes with whatever the realm has become since.
Import the realm **once** to seed it, then manage it as configuration
thereafter — via the admin API, `kcadm`, or a Keycloak operator — and drop
`--import-realm` from the run command. Treat `infra/keycloak/` as the starting
template for clients, roles, and mappers, not as the live source of truth.

**Turn demo mode off.** `SBS_DEMO_MODE=true` exposes
`/app/api/auth/demo-login`, which mints a session carrying tokens for all three
demo personas without authenticating anyone. With it off the route returns 404
and operators sign in through Keycloak at `/app/login`. This is a go-live gate,
not a preference.

---

## 4. PostgreSQL and Redis

Both are best run as **managed services** — you want the backup, failover, and
patching story from your platform rather than from a compose file.

- **PostgreSQL** is the system of record: complaints, batches, `agent_runs`,
  `validation_audit`, approvals, institution certificates and OAuth clients.
- **Redis** carries the arq job queue, the idempotency store, and the HMAC
  replay cache. It is not a cache you can casually flush: losing it drops
  queued Tier-2 batches and the replay-protection window.

Size the connection pool with `SBS_API_DB_POOL_SIZE` (default 10) and
`SBS_API_DB_POOL_MAX_OVERFLOW` (default 20) — **per process**. Total connections
are roughly `(pool_size + overflow) × (API replicas + worker replicas)`. Managed
Postgres tiers have low connection ceilings; check yours before scaling out.

### Migrations

Alembic, config at `api/alembic.ini`:

```bash
cd api && SBS_API_DATABASE_URL="<dsn>" alembic upgrade head
```

Run it as a **pre-deploy step that completes before new application containers
start** — an init container, a Helm pre-install/pre-upgrade hook, or a
deployment-pipeline stage. Do not run migrations from application startup; with
more than one replica they race.

There is a live sharp edge here: `alembic revision --autogenerate` emits four
spurious `op.drop_index` lines because four indexes are created by migrations
and never declared on their models. **Read every generated migration before
applying it** and delete those lines. The full list and the reasoning are in
[HANDOVER-NOTES.md](HANDOVER-NOTES.md#database-and-migrations).

### Backup and restore

The repository ships no backup tooling — this is entirely your platform's job.
What matters for this system specifically:

- **Postgres is the only true system of record.** Continuous WAL archiving or
  your provider's point-in-time restore. `agent_runs` and `validation_audit` are
  audit tables: a supervisory authority will expect them to be recoverable to a
  point in time, not merely restorable to last night.
- **Redis** — a snapshot is worth having so a restart does not drop queued
  batches, but treat Redis as reconstructible and Postgres as authoritative.
- **Batch file storage** (`SBS_API_BATCH_STORAGE_PATH`) holds uploaded Tier-2
  files. It is pruned after `SBS_API_BATCH_STORAGE_PRUNE_DAYS`. Back it up on
  the same schedule as the database if your retention rules cover submissions.
- **A restore you have not rehearsed is not a backup.** The checklist has a line
  for the drill.

---

## 5. Session backend — a real constraint on scaling

**The cockpit's server-side session store is an in-process `Map`, and the Redis
backend is not implemented.** `app/src/auth/session.ts` carries a comment
describing a migration to Redis under `SBS_SESSION_BACKEND=redis`; that variable
is read nowhere, and the app has no Redis client dependency.

The practical consequence:

- **Run exactly one cockpit replica**, or put strict sticky sessions in front of
  it. Two replicas without stickiness will log operators out unpredictably, as
  requests land on a process that has never seen their session id.
- **A cockpit restart logs everyone out.** Sessions do not survive the process.

Neither is acceptable for a highly-available supervisory deployment, and both
are cheap to fix — the store interface in `session.ts` is small and does not
change shape. Implementing it is the honest prerequisite for scaling the
cockpit horizontally. Until then, scale the **API** tier (which is stateless)
and leave the cockpit at one.

The API processes and the worker hold no session state and scale freely.

---

## 6. Observability

OpenTelemetry tracing already exists at
`api/sbs_api/observability/tracing.py`. Point it at your collector:

```bash
SBS_API_OTEL_TRACES_EXPORTER=otlp
SBS_API_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318/v1/traces
SBS_API_OTEL_SERVICE_NAME=sbs-suptech-api      # set per process
```

The exporter is **OTLP over HTTP**, not gRPC — point it at your collector's
HTTP receiver (port 4318 by convention, path `/v1/traces`), not the gRPC port
4317. A gRPC endpoint here fails to export and the traces vanish silently.

`console` is the default and is for development. `none` disables tracing.
Give each process a distinct `OTEL_SERVICE_NAME` — the institution-facing API,
the internal API, and the worker are three services, and a shared name makes
traces unreadable.

Set `SBS_API_LOG_FORMAT=json` in production. Logs are structured and already
carry the trace and correlation ids (`observability/logging.py`), so a
collector that ingests JSON gives you log-to-trace correlation with no further
work.

Readiness and liveness: the API exposes readiness that pings the database with
a `SBS_API_READINESS_DB_PING_TIMEOUT_MS` budget (default 200 ms) and caches the
result for `SBS_API_READINESS_CACHE_SECONDS`. Wire it to your orchestrator's
readiness probe.

What the repository does **not** ship: dashboards, alert rules, or an SLO
definition. There is no metrics exporter — tracing and structured logs are what
exists. Building the alerting layer is a checklist item, and the things worth
alerting on are queue depth, ingestion stall, validator failure rate, signing
failure rate, and readiness flapping.

---

## 7. Worker scaling

The worker consumes the arq queue on Redis and runs the Tier-2 batch pipeline.
It is stateless with respect to any single batch and scales horizontally by
running more replicas against the same Redis.

Two operational rules, both of which have cost time before:

1. **The agent pipeline is off by default.** `SBS_API_AGENTS_PIPELINE_ENABLED`
   defaults to `false`, so a worker started without it ingests batches normally
   and writes **no `agent_runs`**. Nothing looks broken; the analysis is simply
   absent. Set it explicitly.

2. **The sandbox worker mounts the repository read-only and does not pick up
   code changes.** After changing anything under `api/`, the container must be
   recreated — restarting it is not enough:

   ```bash
   SBS_API_AGENTS_PIPELINE_ENABLED=true docker compose up -d --force-recreate worker
   ```

   In a production deployment built from an image this does not arise, because
   a new image means a new container. It matters when you run the compose stack
   as a staging environment, and it is a standing trap there. See
   [HANDOVER-NOTES.md](HANDOVER-NOTES.md#operating-the-stack).

Model provider: `SBS_API_MODEL_PROVIDER` defaults to `on_prem`, which expects a
vLLM endpoint and refuses to boot without one when the pipeline is enabled
(`provider.healthcheck.failed`). **The `on_prem` path has never been observed
against a real vLLM** — that is a checklist item, not a footnote. `replay` is
fixture-backed and logs a warning on every request. `cloud` (Azure OpenAI) has
run live against synthetic data only, behind
`SBS_API_CLOUD_LEGAL_APPROVED=true`. The provider semantics are in
[ARCHITECTURE.md](ARCHITECTURE.md) §3 and the caveats in
[HANDOVER-NOTES.md](HANDOVER-NOTES.md#agents-and-model-providers).

---

## 8. Upgrade procedure

The gate suite is the acceptance test. There are ten gates plus the pytest
suite, and they are the same ones CI runs.

1. **Read the changelog** ([../CHANGELOG.md](../CHANGELOG.md)) for breaking
   changes, and the ADRs referenced by them.
2. **Stage first.** Restore a recent production backup into staging and upgrade
   that, so migrations run once against realistic data before they run against
   real data.
3. **Back up the database**, and confirm the backup is restorable rather than
   merely present.
4. **Run migrations** as a pre-deploy step (§4), reading any generated
   migration first.
5. **Deploy the new image**, worker included. If you run the compose stack,
   recreate the worker rather than restarting it (§7).
6. **Run the gates against the upgraded stack:**

   ```bash
   for s in stage-a stage-b stage-c stage-d stage-e stage-f \
            stage-g-contract stage-g-full stage-h-contract stage-h-full; do
     bash scripts/smoke-test-batch.sh $s
   done
   uv run pytest -q
   ```

   All ten must exit 0. `stage-g-full` and `stage-h-full` include live-stack
   halves that catch a stale worker — which is exactly the failure mode step 5
   guards against, so do not skip them in favour of the contract-only variants.
7. **Walk the cockpit** end to end against the upgraded stack before declaring
   the upgrade done. The gates do not cover the UI.
8. **Rollback** is: redeploy the previous image, and restore the database if the
   upgrade included a migration that is not backward-compatible. Alembic
   downgrades are not maintained as a supported path — plan rollback around the
   backup, not around `alembic downgrade`.

Optionally run `scripts/perf-smoke.sh` for an indicative latency figure. It is
**sandbox-scale only and not a load test** — see the note in that script and the
[OPERATOR-CHECKLIST.md](OPERATOR-CHECKLIST.md) line that requires a real one.

---

## 9. Before you go live

Everything above describes how to run the system. It does not establish that
your deployment is ready to carry regulated traffic — that requires a pen test,
a load test at your volume, certificates from a real CA, tested backups, live
monitoring, and a set of governance decisions specific to your authority.

**→ [OPERATOR-CHECKLIST.md](OPERATOR-CHECKLIST.md)**
