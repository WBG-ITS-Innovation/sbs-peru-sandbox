# SBS SupTech Sandbox — AI-Enabled Conduct Supervision

A synthetic-data reference implementation of a supervisory-technology (SupTech) platform for consumer-complaint ingestion and analytics. Developed by the World Bank ITS Technology & Innovation Office (ITSTI) in support of an engagement with Peru's financial regulator, the Superintendencia de Banca, Seguros y AFP (SBS). Everything in this repository runs locally on synthetic data: it demonstrates a two-tier complaint-data channel (near-real-time API and authenticated batch), an auditable analytics pipeline, and a supervisor cockpit.

This is a prototype for demonstration and reuse, not an official SBS system, and it contains no SBS data.

![Supervisor cockpit](docs/assets/cockpit.png)

## Getting started

Prerequisites: Docker + Docker Compose, Python 3.12 with [uv](https://docs.astral.sh/uv/), Node.js 20+ (for the web app under `app/`), bash, and openssl (for the local dev CA).

A fresh clone reaches a working signed-request stack in three commands:

```bash
# 1. Bring up Postgres + Redis, apply migrations, seed institutions +
#    HMAC secrets, generate the dev CA + leaf certs, seed oauth_clients.
bash scripts/dev-up.sh

# 2. Run the API with mTLS direct mode + the real auth chain, on :8443
#    (the port step 3 and the dev certs' SANs both expect):
SBS_API_MTLS_MODE=direct \
SBS_API_AUTH_STUB_ENABLED=false \
SBS_API_PORT=8443 \
  bash scripts/run-api.sh

# 3. Smoke-test the full signed-request path end-to-end:
bash scripts/smoke-test-auth.sh
```

The legacy auth-stub path is still supported for tests and any local-only
work that does not exercise mTLS:

```bash
bash scripts/dev-up.sh
bash scripts/run-api.sh          # AUTH_STUB_ENABLED=true by default
bash scripts/smoke-test.sh
```

Run `make help` for the full set of convenience targets (tests, smoke suite, corpus regeneration, developer portal, standards pack).

## Run the supervisor cockpit

The cockpit is a separate Next.js app under `app/`. It needs **two API processes**, because the institution-facing channel and the internal channel have deliberately different auth postures:

| Process | Port | Posture | Serves |
|---|---|---|---|
| Institution-facing API | `8443` | mTLS direct, real auth chain, `SBS_API_AUTH_STUB_ENABLED=false` | `POST /v1/complaints`, `POST /v1/batches` — everything an institution calls |
| Internal API | `8000` | Plain HTTP, auth stub on, shared-secret bearer on `/v1/internal/*` | The cockpit's server-side fetches (Next.js → FastAPI, server-to-server) |

Running only the `8443` process leaves the cockpit unable to reach a backend and `/app/cockpit` returns **HTTP 500** with `fetch failed`. That is the most common way to get a broken-looking cockpit.

```bash
# 1. Postgres + Redis + migrations + seeds (as above), plus Keycloak —
#    the supervisor session is Keycloak-backed per ADR 0040. The realm
#    'sbs-demo' is imported automatically from infra/keycloak/.
bash scripts/dev-up.sh
docker compose up -d keycloak

# 2. Institution-facing API on :8443 — step 2 above, plus the agent
#    pipeline, so submitted complaints get an agent chain to show.
SBS_API_MTLS_MODE=direct \
SBS_API_AUTH_STUB_ENABLED=false \
SBS_API_PORT=8443 \
SBS_API_AGENTS_PIPELINE_ENABLED=true \
  bash scripts/run-api.sh

# 3. Internal API on :8000, in a second terminal. This is the one the
#    cockpit talks to; the auth-stub default is what you want here.
SBS_API_PORT=8000 bash scripts/run-api.sh

# 4. Cockpit env. The shared secret must MATCH on both sides:
#    app/.env.local          SBS_INTERNAL_API_SECRET
#    the FastAPI processes   SBS_API_INTERNAL_API_SECRET   (root .env)
cp app/.env.example app/.env.local
# then edit app/.env.local — see the comments in app/.env.example

# 5. Run the cockpit.
cd app && npm install && npm run dev
```

`SBS_API_AGENTS_PIPELINE_ENABLED` defaults to **off**, so a `:8443` process started without it ingests complaints normally but writes no `agent_runs` — the cockpit renders the complaint with an empty agent chain. The Tier-2 equivalent is a separate flag on the worker container; see [docs/HANDOVER-NOTES.md](docs/HANDOVER-NOTES.md) under "Operating the stack".

Then open the demo-mode session bootstrap, which acquires Keycloak tokens for the three demo personas and redirects to the cockpit:

<http://localhost:3000/app/api/auth/demo-login>

The cockpit itself is at **<http://localhost:3000/app/cockpit>** (`/supervisor` is not a route and 404s). `SBS_DEMO_MODE=true` is what exposes `demo-login`; with it off the route returns 404 and you log in through Keycloak normally at `/app/login`.

See [app/README.md](app/README.md) for the route map and [docs/HANDOVER-NOTES.md](docs/HANDOVER-NOTES.md) for the operational caveats worth knowing before a demo.

The canonical OpenAPI YAML is served at `/v1/openapi.yaml`. FastAPI's auto-generated `/openapi.json`, `/docs`, and `/redoc` are disabled per ADR 0028 §6 — the curated YAML is the contract. The running API also serves the rendered developer portal at `/v1/portal/` (Stoplight Elements, vendored locally per ADR 0037, no CDN dependency).

## Architecture

Three layers per [ADR 0001](docs/adr/0001-three-layer-mcp-a2a-langgraph.md) (Accepted): **agents** orchestrate, **tools** execute, **supervisors** approve. Specialist agents (complaint triage, investigation, synthesis, plus scaffolded extensions) drive an in-house tool-calling loop over deterministic tools — classification, data-quality validation against the 27-field Annex 1-A schema, PII redaction, taxonomy normalization — behind a provider-pluggable model interface (`on_prem`, `replay`, `mock`; `cloud` gated off by default). Every run is recorded as an auditable `agent_run` (see [docs/schemas/](docs/schemas/)).

See [docs/adr/](docs/adr/) for all architectural decision records (current head: ADR 0045).

## Data

All complaint records in this repository are synthetic. The committed golden sample (`data/synthetic-corpus-golden/`, 200 rows per demo institution, checksummed manifests) is produced by a seeded, deterministic generator; regenerate with `make corpus-golden`. Demo personas use reserved `@sandbox.example.com` addresses. See [docs/DATA_PROVENANCE.md](docs/DATA_PROVENANCE.md) and ADR 0036 (synthetic-corpus fidelity tiers).

## For institutional integrators

If you are an institution integrating with the SBS sandbox:

1. **Read the portal.** Open `http://<host>/v1/portal/`. The portal renders the canonical OpenAPI 3.1 specification interactively. "Try It" is disabled because mTLS cannot be satisfied from a browser — actual integration uses curl plus the helpers below.

2. **Download the standards pack** as a versioned tarball, with the OpenAPI spec, JSON Schemas, error catalog, webhook-verification helpers, OpenAPI Generator recipes, example payloads, and a provenance manifest:
```bash
   make standards-pack
```
   See [standards-pack/README.md](standards-pack/README.md) for the contents and verification steps.

3. **Use the SDK helpers.** Python integrators install `sdk-helpers/python/` (pure stdlib, Python 3.10+). Node.js integrators install `sdk-helpers/typescript/` (dual ESM + CJS). Both implement the webhook signature verification surface and round-trip against the server's outbound signer in CI. Java and Go integrators use the tested reference snippets at `standards-pack/recipes/webhook-verification-{java,go}.md`; .NET integrators adapt the Java snippet via the `openapi-generator-csharp-netcore.md` recipe.

4. **Try the demo replay.** With docker compose running:
```bash
   docker compose up -d worker webhook-listener
   bash scripts/demo.sh --scale small --seed 20260520
```
   Generates 51 deterministic synthetic complaints (17 per institution × 3 demo institutions), uploads them as Tier 2 batches, polls until each completes, and tails the webhook-listener for the three PASS lines.

Integrator-surface ADRs: [0037 portal serving](docs/adr/0037-developer-portal-serving-mechanism.md) · [0038 SDK helpers](docs/adr/0038-sdk-helper-scope-and-distribution.md) · [0039 standards pack](docs/adr/0039-standards-pack-v0-1-distribution-and-manifest.md).

## Documentation

- [docs/HANDOVER-NOTES.md](docs/HANDOVER-NOTES.md) — operational sharp edges, deliberate limitations, errata
- [docs/adr/](docs/adr/) — architectural decision records
- [docs/DATA_PROVENANCE.md](docs/DATA_PROVENANCE.md) — synthetic-data provenance
- [docs/demo/institution-api-workflow.md](docs/demo/institution-api-workflow.md) — institution API walkthrough
- [docs/DEPLOY.md](docs/DEPLOY.md) — deployment scaffold
- [CONTRIBUTING.md](CONTRIBUTING.md) — contributor guide
- [api/openapi/error-catalog.md](api/openapi/error-catalog.md) — stable error codes

## License

This project is licensed under the MIT License together with the World Bank IGO Rider. The Rider is purely procedural: it reserves all privileges and immunities enjoyed by the World Bank, without adding restrictions to the MIT permissions. Please review both files before using, distributing or contributing.

See [LICENSE](LICENSE) and [WB-IGO-RIDER.md](WB-IGO-RIDER.md).

## Contact

World Bank ITS Technology & Innovation Office (ITSTI) — omakhlouk@worldbank.org
