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
ADR 0028 §6 — the curated YAML is the contract. To render it locally as
a navigable portal:

```bash
bash scripts/serve-devportal.sh
```

## Documentation

- [docs/PLAN.md](docs/PLAN.md) — build plan and progress
- [docs/DECISIONS.md](docs/DECISIONS.md) — decision log
- [docs/adr/](docs/adr/) — architectural decision records (current head: ADR 0033)
- [docs/DEMO.md](docs/DEMO.md) — demo script
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — workflow + branch conventions
- [api/openapi/error-catalog.md](api/openapi/error-catalog.md) — stable error codes
