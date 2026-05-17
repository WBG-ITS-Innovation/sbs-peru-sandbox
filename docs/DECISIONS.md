# Decisions Log

One line per non-trivial decision. Date | decision | rationale.

## Format

YYYY-MM-DD | [PartN] decision summary | one-line rationale.

## Entries

2026-05-16 | [Part1] Retired `scripts/requirements-harness.txt`; harness deps live in root `pyproject.toml` `dev` group; install via `uv sync` | uv project initialization (Prompt 3). See ADR 0021.
2026-05-17 | [Part1] Locked May 25 sprint kickoff scope: Parts 2/3/4 full, Parts 5/6/7/8/11 reduced, Parts 9/10 deferred entirely; PLAN.md restructured with per-Part May 25 scope subsections | May 25 sprint kickoff scope-lock (Prompt 4). See ADR 0025.
2026-05-18 | [Part2] Anexo 1-A May 25 sandbox uses a curated 15-field subset reconciled against Resolución SBS N° 04036-2022; full code lists + PII fields deferred to Part 11 | Prompt 5. See ADR 0026.
2026-05-18 | [Part2] OpenAPI 3.1 specification at api/openapi/sbs-api-v1.yaml is the canonical contract; Pydantic v2 models implement it; JSON Schemas exported; match-test enforces alignment | Prompt 5. See ADR 0027.
2026-05-18 | [Part2] RFC 9457 problem+json is the SBS error envelope; placeholder `type` namespace pending SBS sign-off; error catalog committed at api/openapi/error-catalog.md | Prompt 5. Tracked in docs/sessions/2026-05-18-prompt-05-open-questions.md.
2026-05-18 | [Part2] Developer portal uses Stoplight Elements (CDN) with Redoc 2.x as documented fallback; vendoring deferred to Part 7 / Prompt 9 | Prompt 5. See docs/research/2026-05-18-prompt-05-stack-validation.md §E.
