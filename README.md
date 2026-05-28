# SBS SupTech Prototype

Reference implementation of a multi-agent supervisory technology platform for consumer complaint ingestion and analytics. Built for SBS Peru.

## Architecture

Three-layer agent architecture:
- **MCP** (Model Context Protocol) — tools and data sources
- **A2A** (Agent-to-Agent) — inter-agent communication
- **LangGraph** — internal agent state machines

See [docs/adr/](docs/adr/) for architectural decisions.

## Status

In active development. See [docs/PLAN.md](docs/PLAN.md) for current state.

## Quickstart

A fresh clone reaches a working signed-request stack in three commands:

```bash
# 1. Bring up Postgres + Redis, apply migrations, seed institutions +
#    HMAC secrets, generate the dev CA + leaf certs, seed oauth_clients.
bash scripts/dev-up.sh

# 2. Run the API with mTLS direct mode + the real auth chain
#    (workstreams A/B/C/E/F.7 lit up):
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

The canonical OpenAPI YAML is served at `/v1/openapi.yaml`. FastAPI's
auto-generated `/openapi.json`, `/docs`, and `/redoc` are disabled per
ADR 0028 §6 — the curated YAML is the contract. The running API also
serves the rendered developer portal at `/v1/portal/` (Stoplight
Elements, vendored locally per ADR 0037, no CDN dependency).

## For institutional integrators

If you are an institution integrating with the SBS sandbox:

1. **Read the portal.** Open `http://<host>/v1/portal/` (Lima sandbox
   host TBD pending SBS confirmation). The portal renders the
   canonical OpenAPI 3.1 specification interactively. "Try It" is
   disabled because mTLS cannot be satisfied from a browser — actual
   integration uses curl plus the helpers below.

2. **Download the standards pack** as a versioned tarball. v0.1.0 lands
   here at sprint kickoff with the OpenAPI spec, JSON Schemas, error
   catalog, hand-maintained webhook-verification helpers, OpenAPI
   Generator recipes, example payloads, and a provenance manifest:
   ```bash
   make standards-pack    # produces dist/standards-pack-v0.2.0.tar.gz
   ```
   See [standards-pack/README.md](standards-pack/README.md) for the
   contents and verification steps.

3. **Use the SDK helpers.** Python integrators install
   `sdk-helpers/python/` (pure stdlib, no `cryptography` dependency
   — installs anywhere Python 3.10+ runs). Node.js integrators install
   `sdk-helpers/typescript/` (dual ESM + CJS exports). Both implement
   the webhook signature verification surface and round-trip against
   the server's outbound signer in CI. Java and Go integrators use
   the tested ~30-line reference snippets at
   `standards-pack/recipes/webhook-verification-{java,go}.md`. .NET
   integrators adapt the Java snippet via the
   `standards-pack/recipes/openapi-generator-csharp-netcore.md`
   recipe.

4. **Try the demo replay.** With docker compose running:
   ```bash
   docker compose up -d worker webhook-listener
   bash scripts/demo.sh --scale small --seed 20260520
   ```
   Generates 51 deterministic synthetic complaints (17 per institution
   × 3 demo institutions), uploads them as Tier 2 batches, polls until
   each completes, and tails the webhook-listener for the three PASS
   lines. Output lands in `tmp/demo-run/<timestamp>/`.

ADRs that document the v0.1 institutional-integrator surface:
[ADR 0037 portal serving](docs/adr/0037-developer-portal-serving-mechanism.md) /
[ADR 0038 SDK helpers](docs/adr/0038-sdk-helper-scope-and-distribution.md) /
[ADR 0039 standards pack](docs/adr/0039-standards-pack-v0-1-distribution-and-manifest.md).

## Documentation

- [docs/PLAN.md](docs/PLAN.md) — build plan and progress
- [docs/DECISIONS.md](docs/DECISIONS.md) — decision log
- [docs/adr/](docs/adr/) — architectural decision records (current head: ADR 0039)
- [docs/DEMO.md](docs/DEMO.md) — demo script
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — workflow + branch conventions
- [api/openapi/error-catalog.md](api/openapi/error-catalog.md) — stable error codes
