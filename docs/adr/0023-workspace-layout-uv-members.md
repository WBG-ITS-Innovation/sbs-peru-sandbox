# ADR 0023 — Workspace layout: uv workspace, four members

- **Status:** Accepted
- **Date:** 2026-05-16
- **Target prompt / Part:** Prompt 3 / Part 1
- **Supersedes:** —
- **Superseded by:** —

## Context

The repo will hold four Python packages by Part 7: a FastAPI service (`api/`), an agent layer (`agents/`), MCP tool servers (`tools/`), and a client SDK (`sdk/`). Each will have its own dependency surface — the SDK needs vendor-flexible HTTP clients; the agent layer needs LangGraph and MCP; the API needs FastAPI and database drivers; the tool layer needs whatever the tools touch. The repo also holds non-Python work: a frontend (Part 8, JS/TS toolchain) and infrastructure (Part 9, Terraform + Helm). The maintainer is solo and the codebase will be handed off to a vendor — a layout that splits cross-cutting changes across separate repos would cost coordination time the maintainer cannot spend.

## Decision

The repo is a single uv workspace. Workspace members are `api/`, `agents/`, `tools/`, `sdk/`, each with its own `pyproject.toml` for package-local dependencies. The root `pyproject.toml` declares shared dev dependencies (the harness deps in the `dev` group) and the workspace member list. `uv.lock` at the root is shared across all members; transitive dependencies resolve once and identically.

`frontend/` and `infra/` are not workspace members (different toolchains). Per-member Python layout is flat — for example, `api/sbs_api/...` rather than `api/src/sbs_api/...` — until a packaging concern forces the conversion to src-layout.

## Precedent

See [docs/research/supply-chain-precedents.md, §6 — "Python project toolchain"](../research/supply-chain-precedents.md#6-python-project-toolchain), second paragraph. Comparators cited: (1) uv's own workspace documentation at [docs.astral.sh/uv/concepts/projects/workspaces/](https://docs.astral.sh/uv/concepts/projects/workspaces/) defines the multi-member-with-shared-lockfile pattern, and the `astral-sh/uv` repository is itself structured as a workspace; (2) Cargo workspaces (Rust, 2017 onward) — the canonical cross-language reference for the same pattern, mature for years; (3) pnpm workspaces (JavaScript, 2019 onward) — the same pattern in the JS ecosystem, well-understood. Three independent language toolchains converging on the same shape is the strongest precedent evidence available; the pattern is not a uv-specific bet.

## Divergence

The alternative is a single flat root package with all code under `sbs_suptech/`. We diverge because the SDK will need independent versioning once supervised institutions integrate against it (Part 7), and the API and agent codebases will diverge enough in dependency surface that a flat layout would mislead a reviewer about what each package actually needs.

A second alternative is separate repositories (multi-repo). We diverge because the maintainer is solo and the build is end-to-end one-commit refactors — a multi-repo split would cost coordination time that does not exist.

A minor sub-decision: flat layout (`api/sbs_api/...`) rather than src-layout (`api/src/sbs_api/...`). The src-layout is the safer choice for packages that will be published, because it prevents the test runner from picking up the in-tree source instead of the installed wheel. We choose flat for now because no member is published yet, and the conversion to src-layout is mechanical when the SDK starts to ship to PyPI in Part 7. The flat-layout sub-decision is revisited at that time, not earlier.

## Consequences

- Cross-cutting changes touching multiple members land atomically in one commit and one PR.
- A reviewer can see exactly what each member depends on by reading the member's `pyproject.toml`.
- The SDK member is structured so that its Part-7 publication does not require restructuring the rest of the repo.
- The `frontend/` and `infra/` directories are placeholders (with `.gitkeep` markers) until their respective Parts land; uv's workspace globbing does not include them.
- Each workspace member currently declares `[tool.uv] package = false` because no member ships application code yet. When real packages land (api/ in Part 2, sdk/ in Part 3, tools/ in Part 5, agents/ in Part 6), each member's `pyproject.toml` will gain a build backend (hatchling) and the `package = false` line will be removed.
