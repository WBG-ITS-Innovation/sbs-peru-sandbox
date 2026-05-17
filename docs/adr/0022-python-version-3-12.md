# ADR 0022 — Python version: 3.12

- **Status:** Accepted
- **Date:** 2026-05-16
- **Target prompt / Part:** Prompt 3 / Part 1
- **Supersedes:** —
- **Superseded by:** —

## Context

The project must pin a Python version (or a supported range) for the application code that lands from Part 2 onward. Python 3.12 entered support in 2023; 3.13 in 2024; 3.14 in 2025. Each release adds language and standard-library features; not all libraries in the locked architectural stack track the leading edge equally. The deployment target is on-premises at SBS Peru, controlled end-to-end by this codebase.

## Decision

The project targets Python 3.12 exclusively. `.python-version` pins to `3.12` (minor only — uv selects the current patch). `pyproject.toml` declares `requires-python = ">=3.12,<3.13"` at the root and at each workspace member. CI does not matrix-test against 3.11 or 3.13. The deployment runtime is one we control; multi-version testing buys portability we do not need.

## Precedent

See [docs/research/supply-chain-precedents.md, §7 — "Python version pinning"](../research/supply-chain-precedents.md#7-python-version-pinning). Comparators cited: (1) vLLM, in this project's locked architectural stack, declares `requires-python = ">=3.10,<3.15"` and classifies Python 3.10 through 3.14 as supported in its `pyproject.toml` — 3.12 sits in the supported range; (2) the Model Context Protocol Python SDK declares `requires-python = ">=3.10"` and classifies the same range — again, 3.12 is supported; (3) the established containerized-on-premises application pattern (in contrast to the library pattern represented by Pydantic, which matrix-tests across minors for portability) — pin one minor, do not matrix-test, because the deployment target is fixed and a contributor on a different local version is blocked at `uv sync` by the `requires-python` floor, not at runtime. The decisional pattern adopted here is the application pattern, not the library pattern.

## Divergence

The cautious alternative is to support 3.11 and 3.12, or 3.12 and 3.13, with a CI matrix. We diverge for two reasons.

First, the deployment target is fixed: SBS will run a single base image with a single Python version in production, and a contributor who runs a different local version is blocked at `uv sync` by the `requires-python` floor — there is no portability gap to hedge against.

Second, a CI matrix doubles the CPU and minute budget without proportional return; for a regulator-grade reference implementation that wants its CI to be cheap and predictable, the matrix is a cost we choose not to take on.

A second alternative is to track Python 3.13 once its stack-completeness matches 3.12's. We do not adopt this today because the locked architectural stack (FastAPI, Pydantic v2, SQLAlchemy 2.0 async, vLLM client, LangGraph) is verified at 3.12 and the marginal language features in 3.13 are not worth a churn cycle. A future ADR can move the floor to 3.13 when the rest of the stack-version check holds.

## Consequences

- A contributor on a local Python 3.11 or 3.13 is blocked at `uv sync` with a clear error from the `requires-python` floor.
- uv installs and manages the 3.12 interpreter via `python-build-standalone`. Contributors do not need to install Python separately; `uv python install 3.12` is documented in [docs/setup/uv-quickstart.md](../setup/uv-quickstart.md).
- If a future stack member requires a different version, this ADR is superseded; it is not amended in place.
- The CI pipeline runs against one version (3.12), keeping CI behavior straightforward to diagnose.
