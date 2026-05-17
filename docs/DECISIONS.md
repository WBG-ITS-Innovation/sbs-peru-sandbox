# Decisions Log

One line per non-trivial decision. Date | decision | rationale.

## Format

YYYY-MM-DD | [PartN] decision summary | one-line rationale.

## Entries

2026-05-16 | [Part1] Retired `scripts/requirements-harness.txt`; harness deps live in root `pyproject.toml` `dev` group; install via `uv sync` | uv project initialization (Prompt 3). See ADR 0021.
2026-05-17 | [Part1] Locked May 25 sprint kickoff scope: Parts 2/3/4 full, Parts 5/6/7/8/11 reduced, Parts 9/10 deferred entirely; PLAN.md restructured with per-Part May 25 scope subsections | May 25 sprint kickoff scope-lock (Prompt 4). See ADR 0025.
