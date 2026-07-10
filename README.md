# SBS SupTech Sandbox — AI-Enabled Conduct Supervision

A synthetic-data reference implementation of a supervisory-technology (SupTech) platform for consumer-complaint ingestion and analytics. Developed by the World Bank ITS Technology & Innovation Office (ITSTI) in support of an engagement with Peru's financial regulator, the Superintendencia de Banca, Seguros y AFP (SBS). Everything in this repository runs locally on synthetic data: it demonstrates a two-tier complaint-data channel (near-real-time API and authenticated batch), an auditable analytics pipeline, and a supervisor cockpit.

This is a prototype for demonstration and reuse, not an official SBS system, and it contains no SBS data.

<!-- Optional: add a cockpit screenshot before publication (synthetic data only): -->
<!-- ![Supervisor cockpit](docs/assets/cockpit.png) -->

## Getting started

Prerequisites: Docker + Docker Compose, Python 3.12 with [uv](https://docs.astral.sh/uv/), Node.js 20+ (for the web app under `app/`), bash, and openssl (for the local dev CA).

A fresh clone reaches a working signed-request stack in three commands:

```bash
# 1. Bring up Postgres + Redis, apply migrations, seed institutions +
#    HMAC secrets, generate the dev CA + leaf certs, seed oauth_clients.
bash scripts/dev-up.sh

# 2. Run the API with mTLS direct mode + the real auth chain:
SBS_API_MTLS_MODE=direct \
SBS_API_AUTH_STUB_ENABLED=false \
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

- [docs/adr/](docs/adr/) — architectural decision records
- [docs/DATA_PROVENANCE.md](docs/DATA_PROVENANCE.md) — synthetic-data provenance
- [docs/demo/institution-api-workflow.md](docs/demo/institution-api-workflow.md) — institution API walkthrough
- [docs/DEPLOY.md](docs/DEPLOY.md) — deployment scaffold
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — contributor guide
- [api/openapi/error-catalog.md](api/openapi/error-catalog.md) — stable error codes

## License

This project is licensed under the MIT License together with the World Bank IGO Rider. The Rider is purely procedural: it reserves all privileges and immunities enjoyed by the World Bank, without adding restrictions to the MIT permissions. Please review both files before using, distributing or contributing.

See [LICENSE](LICENSE) and [WB-IGO-RIDER.md](WB-IGO-RIDER.md).

## Contact

World Bank ITS Technology & Innovation Office (ITSTI) — sbs-suptech-sandbox@worldbank.org
