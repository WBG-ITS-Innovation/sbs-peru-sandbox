# Decisions Log

One line per non-trivial decision. Date | decision | rationale.

## Format

YYYY-MM-DD | [PartN] decision summary | one-line rationale.

## Entries

2026-05-16 | [Part1] Retired `scripts/requirements-harness.txt`; harness deps live in root `pyproject.toml` `dev` group; install via `uv sync` | uv project initialization (Prompt 3). See ADR 0021.
