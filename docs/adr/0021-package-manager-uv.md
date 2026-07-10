# ADR 0021 — Package manager: uv

- **Status:** Accepted
- **Date:** 2026-05-16
- **Target prompt / Part:** Prompt 3 / Part 1
- **Supersedes:** —
- **Superseded by:** —

## Context

The repository needs a Python package manager and project tool that will be used through 2028 and beyond. Through 2023–2024 the dominant pattern was pip + pip-tools + venv (or virtualenv). Through 2025–2026 a generation of newer tools converged: Poetry, Hatch, Rye, and uv (Astral). Each addresses gaps in the older pattern — lockfile-first reproducibility, project metadata in `pyproject.toml`, dependency-group support. They differ on resolver speed, workspace support, build-system flexibility, release cadence, and maintainership status.

Through Prompt 2, harness dependencies lived in `scripts/requirements-harness.txt` and were installed via `pip install -r`. The Prompt 2 retrospective named the cutover to a uv-managed project as Part 3 work. Prompt 3 is that cutover.

## Decision

uv (Astral) is the package manager and project tool. The root `pyproject.toml` is the canonical source of dependency truth. `uv.lock` is committed. The repo is a uv workspace; members live under `api/`, `agents/`, `tools/`, `sdk/` — locked separately in [ADR 0023](0023-workspace-layout-uv-members.md). The dev dependency group at the root holds the harness deps that previously lived in `scripts/requirements-harness.txt` (`openai`, `python-dotenv`, `gitpython`, `pyyaml`, `pytest`); the file is retired in the same PR as this ADR.

Inside container builds (Part 5 onward), `pip install` against a `requirements.txt` exported from uv (`uv export`) is acceptable, since the container image does not need uv at runtime. Outside containers, `uv sync` is the only sanctioned install path.

## Precedent

See [docs/research/supply-chain-precedents.md, §6 — "Python project toolchain"](../research/supply-chain-precedents.md#6-python-project-toolchain), first paragraph. Comparators cited: (1) Astral self-hosts on uv across its first-party projects (`astral-sh/uv`, `astral-sh/ruff`, `astral-sh/ty`), each shipping a committed `uv.lock`; (2) FastAPI — in this project's locked architectural stack — documents uv as the recommended modern path, with its [Virtual Environments guide](https://fastapi.tiangolo.com/virtual-environments/) stating "If you are ready to adopt a tool that manages everything for you (including installing Python), try uv"; (3) the Anthropic-published Model Context Protocol Python SDK ([modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)) declares `[tool.uv]` with `required-version = ">=0.9.5"` in its `pyproject.toml`, signaling uv as the supported development toolchain. The pattern uv satisfies is lockfile-first resolution with native workspace support and a Rust-implemented resolver.

## Divergence

Two divergences from precedent are worth naming.

The first is from the conservative `pip-tools` + `venv` pattern that dominated 2023–2024. We diverge because lockfile-first ergonomics and workspace support are decisive for our layout, and because uv has been production-stable through 2025–2026 across the projects cited in the research file. `pip-tools` remains a valid fallback for a contributor who cannot install uv; the documented escape hatch is `uv export > requirements.txt` followed by `pip install -r requirements.txt`, which is also the container-build pattern.

The second is from Poetry. Poetry is the most widely deployed of the newer Python tools and has the largest install base. We diverge because uv's PEP 621 compatibility was complete earlier, its resolver is meaningfully faster on cold installs (relevant for CI cost), and its release cadence has been higher across the comparison window. Hatch and Rye are not divergences worth defending separately — Hatch is competitive on the build-system side but lacks a workspace primitive (workspaces are locked separately in [ADR 0023](0023-workspace-layout-uv-members.md)); Rye is no longer developed and its README explicitly points users to uv as the successor project.

## Consequences

- Contributors install uv once, then run `uv sync` to install all project + dev dependencies in a single command. The install path on the WBG-issued laptop this prompt was developed on was `pip install uv` against the system Python 3.9; see [docs/setup/uv-quickstart.md](../setup/uv-quickstart.md) for the documented options.
- `uv.lock` is committed and is the source of truth for what is installed. Reviewers diff it on every dependency change.
- The container build (Part 5 onward) uses `uv export` to produce a hash-pinned `requirements.txt` fed to pip in the Dockerfile. The runtime image does not carry uv.
- If a contributor cannot install uv (admin restrictions on a managed laptop, a locked-down corporate proxy), the documented fallback is `uv export > /tmp/requirements.txt && pip install -r /tmp/requirements.txt` against a manually-created venv. This is an escape hatch, not a supported steady state.
- uv tracks its own minor releases on a release-train cadence; the contributor's installed uv version may not match the project's developed-against version. The `pyproject.toml` does not currently declare `[tool.uv] required-version`. Revisit if version drift causes friction.

## Flagged for cross-review

Maturity for a regulator-grade project that must be maintainable in 2028 and beyond. uv has fewer years of production use than pip-tools, but Astral's self-hosting, FastAPI's recommendation, and the MCP SDK's requirement (all cited in §6) are first-party signals from the projects that would suffer most if uv proved unstable. Cross-review owner: Maintainer. The triage line will record whether the maintenance horizon argues for a slower-moving tool, or whether the precedents already cited carry the decision.
