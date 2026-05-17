---
title: Supply chain, secrets, and software-provenance precedents
date: 2026-05-16
source: Initial set distilled during Prompt 2 (Part 1, supply chain & secrets), drawing on widely-known open-source security practice and public-sector repository conventions.
status: Living document — append-only revisions tracked in git history
---

# Supply chain, secrets, and software-provenance precedents

This document collects the operational precedents the platform's tooling is built on: secret scanners, dependency-update tooling, SBOM format, dependency-review thresholds, environment-variable handling, image signing, provenance attestation, and related supply-chain decisions. It is the citation target for ADRs that lock infrastructure-of-the-build decisions — distinct from [market-comparators.md](market-comparators.md), which covers the regulator-domain comparator landscape (CFPB, BCB, FCA, AFCA, CONDUSEF, etc.).

Both files are valid citation targets for ADR `## Precedent` sections. The `benchmark-checker` subagent accepts a citation pointing to a specific section of any research file under `docs/research/`. The rule is specificity — name the section and the comparator — not the filename.

## 1. Secret-scanner stacks

The two-scanner pattern (gitleaks for high-confidence pattern matches, detect-secrets for entropy-plus-baseline) is the default in mature open-source security tooling. Yelp built and open-sourced `detect-secrets` to enforce a baseline-aware scan at commit time; the project explicitly addresses the "every UUID is a false positive" failure mode by gating findings against a committed baseline. `gitleaks` is the de-facto match for high-signal pattern detection (AWS keys, GitHub tokens, JWTs, Slack tokens) and is widely used in open-source infrastructure repositories, including in CI on repos such as `cilium/cilium` and several Kubernetes SIG repos. CFPB's open-source projects on github.com/cfpb run gitleaks in CI. The common pattern is: both scanners locally, gitleaks-only in CI, detect-secrets baseline committed as a developer aid.

## 2. Dependency update tooling in regulator / government repos

GitHub-native Dependabot is the default in comparable public-sector repos: US 18F (`18F/*`), UK Government Digital Service (`alphagov/*`, including GOV.UK Pay and Notify), UK HMRC's open-source organisation (`hmrc/*`), Canada's CDS (`cds-snc/*`), and Singapore GovTech (`opengovsg/*`). Renovate is the strong alternative and is preferred in some commercial fintech contexts, with the trade-off being more configuration surface area in exchange for finer-grained scheduling and grouping. The pattern in regulator-facing repos is to start with Dependabot and migrate to Renovate only when grouping or scheduling demands exceed what Dependabot can express.

## 3. SBOM format

CycloneDX (OWASP) and SPDX (Linux Foundation) are the two practical choices. CISA's "Minimum Elements for a Software Bill of Materials" (2021) is format-neutral, but the supporting tooling ecosystem has consolidated around CycloneDX JSON in OpenSSF-funded projects, in Anchore's `syft` (which emits both formats but defaults to CycloneDX), and in Sigstore's release artifact attestations. The German BSI's "Technical Guideline TR-03183" recognises both. CycloneDX JSON, produced by `syft`, is the most-supported pipeline shape — Trivy, Grype, Dependency-Track, and OpenSSF Scorecard all consume it without an adapter. This is the format the SBS handoff package will produce.

## 4. Dependency-review thresholds

GitHub's `dependency-review-action` exposes a `fail-on-severity` knob with values `low`, `moderate`, `high`, `critical`. The defensible threshold for a pre-pilot codebase is `high`: blocking on `moderate` produces enough false-positive friction (transitive-only, advisory-not-applicable) to push contributors to skip the gate, which is worse than letting moderates through with visibility. Several CFPB and UK GDS open-source repos use `high` as their default; production-tier projects tighten the bar to `moderate` once the noise floor is understood. The threshold is a parameter, not a posture; SBS revisits it at Part 9.

## 5. Environment-variable / secret handling

The 12-factor app methodology (factor III, "Config") is the foundational precedent for `.env`-style configuration: secrets in environment, never in code, never in version control. GitHub's own "About secret scanning" guidance and "Managing encrypted secrets in your repository and organization" pages codify the modern enforcement layer: gitignore the `.env`, scan for committed secrets, store CI-time secrets in the platform's encrypted-secret store, and rotate on exposure. The CFPB, FCA, and HMRC open-source repos follow this pattern uniformly. SBS's contribution here is per-tool wiring (Azure OpenAI four-variable shape, WBG ITS tenancy), not a new posture.

## 6. Python project toolchain

The lockfile-first Python toolchains in production use as of 2026 are uv (Astral), Poetry, Hatch, and pip-tools + venv. Rye was the immediate predecessor in Astral's lineup and is no longer developed; its [README](https://github.com/astral-sh/rye) points all users to uv as "the successor project from the same maintainers, which is actively maintained and much more widely used," and Rye's own dependency-installation backend is uv. Astral self-hosts on uv across its first-party projects (`astral-sh/uv`, `astral-sh/ruff`, `astral-sh/ty`), each shipping a committed `uv.lock`. FastAPI — in this project's locked architectural stack — documents uv as the recommended modern path; its [Virtual Environments guide](https://fastapi.tiangolo.com/virtual-environments/) states "If you are ready to adopt a tool that manages everything for you (including installing Python), try uv," and presents uv tabs alongside pip throughout the install instructions. Anthropic's Model Context Protocol Python SDK ([modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)) declares `[tool.uv]` with `required-version = ">=0.9.5"` in its `pyproject.toml`, signaling uv as the supported development toolchain. The named alternatives carry different trade-offs: Poetry is widely deployed but its PEP 621 compatibility lagged uv's and its release cadence has been lower across 2025–2026; Hatch is competitive on the build-system side but does not provide a workspace primitive; pip-tools + venv is the conservative 2023–2024 baseline that all four newer tools were built to replace.

The multi-member workspace pattern — a root manifest, per-member packages, and a single shared lockfile — is mature across language toolchains. Cargo (Rust) has shipped workspaces since 2017; pnpm (JavaScript) since 2019. uv's workspaces are documented at [docs.astral.sh/uv/concepts/projects/workspaces/](https://docs.astral.sh/uv/concepts/projects/workspaces/), and the `astral-sh/uv` repository is itself structured as a workspace. The decisional value comes from two things. Cross-cutting changes stay atomic — a refactor that touches the API package and an agent package lands in one commit, with one lockfile resolution, on one branch. And per-member dependency surfaces stay explicit: a reviewer can see exactly what the `api/` package needs versus what the `agents/` package needs, rather than reading a single flat dependency set that mixes the two and may mislead. The alternative single-root-flat-package layout is appropriate when every member shares an identical dependency surface and no member will ever be published independently; that is not the case for a service repository where the SDK package will need independent versioning once supervised institutions integrate against it.

## 7. Python version pinning

Python applications that control their own deployment runtime — on-premises services, containerized backends, vendor-shipped reference implementations — pin one Python minor version per project rather than matrix-testing across multiple minors. This is distinct from the library pattern, where matrix-testing across a supported range is the norm because the library's deployment target is whatever its consumers happen to run. Pydantic, in this project's locked architectural stack, sits firmly in the library pattern: it supports a wide range of Python minors because its consumers vary. vLLM, also in the stack, declares `requires-python = ">=3.10,<3.15"` and classifies Python 3.10 through 3.14 as supported in its `pyproject.toml`; that is the supported range, not a deployment recommendation. The MCP Python SDK declares `requires-python = ">=3.10"` and classifies the same range. The application-pattern decision being adopted here — pin one current minor, do not matrix-test — is justified by the fact that the deployment runtime is fixed (on-premises at SBS, a single base image), and a contributor on a different local version is blocked at `uv sync` by the `requires-python` floor, not at runtime. The practical mechanic is: `pyproject.toml`'s `requires-python` is the gate, `.python-version` is the convention uv reads to select the managed interpreter, and the absence of a CI matrix is the explicit choice not to spend cycles on portability the deployment target does not require.

## Future sections — placeholder list of supply-chain precedent areas not yet covered

As tooling decisions are locked, additional sections will be appended. The entries below are stubs reserving numbering for areas the platform will lock later in the build; they are movable until their target Part lands.

- **8. Image signing.** Sigstore / cosign adoption patterns in regulator-adjacent OSS. Locked in Part 9.
- **9. Provenance attestation.** SLSA framework levels and what attestations OpenSSF Scorecard checks. Locked in Part 9.
- **10. License-compliance scanning.** ScanCode, FOSSA, or `syft`-derived license metadata against an approved-list policy. Locked in Part 9.
- **11. Container scanning.** Trivy / Grype in CI against a vulnerability-database freshness policy. Locked in Part 9 once images exist.

Append-only edits below this line tracked in git history.
