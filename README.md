# SBS SupTech Prototype

Reference implementation of a multi-agent supervisory technology platform for consumer complaint ingestion and analytics. Built for SBS Peru.

## Architecture

Three-layer agent architecture:
- **MCP** (Model Context Protocol) — tools and data sources
- **A2A** (Agent-to-Agent) — inter-agent communication
- **LangGraph** — internal agent state machines

See `/docs/adr/` for architectural decisions.

## Status

In active development. See `/docs/PLAN.md` for current state.

## Quickstart

```bash
docker compose up -d
uv sync
uv run alembic upgrade head
uv run uvicorn api.main:app --reload
```

API docs: http://localhost:8000/docs
Grafana: http://localhost:3001

## Documentation

- `/docs/PLAN.md` — build plan and progress
- `/docs/DECISIONS.md` — decision log
- `/docs/adr/` — architectural decision records
- `/docs/DEMO.md` — demo script