# Security policy

This project handles complaint data on behalf of a financial regulator. Security findings are taken seriously, including those in the workflow harness and tooling.

## Reporting a vulnerability

**Do not** open a public GitHub issue for a security vulnerability.

**WBG-internal reporters** (World Bank Group staff and contractors): contact the maintainer through internal channels first. This is the fastest path during the active build phase.

**External reporters**: a `security@<TBD>` alias will be provisioned before this project is opened beyond core contributors. Until then, contact the maintainer through the address listed in the repository profile on github.com.

Include:

- A description of the issue and the impact you believe it has.
- Steps to reproduce, or a proof-of-concept if you have one.
- The branch / commit / version where you observed it.
- Whether you would like to be credited in the fix, and the name to credit.

Expected response time during the active build phase: **two business days** to acknowledge, **ten business days** to triage and propose a path to remediation.

## Scope

In scope:

- The SBS SupTech Prototype codebase in this repository, all branches.
- The workflow harness in `.claude/`, `scripts/`, and the GitHub Actions workflows.
- Any infrastructure-as-code (Helm, Terraform) in this repository.

Out of scope (report directly to the relevant project):

- Vulnerabilities in third-party dependencies (please report upstream — Dependabot watches them here).
- Vulnerabilities in the runtime infrastructure of any specific deployment (those belong to that operator).

## Supported branches

During the active build phase, only the `main` branch is in active maintenance. Long-lived feature branches (`part-NN/...`) are evaluated case-by-case.

## No personal data in issues, PRs, or commits

This repository must not contain real personal data, real complaint content, real institution credentials, or real cryptographic material. That includes:

- Real complaint narratives, even partial or paraphrased.
- Real names, contact details, or document numbers belonging to actual people.
- Production credentials, even expired ones — rotate, then redact.
- Real certificates, private keys, or signing material.

If a reproduction case needs realistic data, use the synthetic generator that ships in `scripts/` (added in Part 4). Synthetic data is clearly labelled as such.

If a real secret is committed, the response is: **rotate the secret first, then expunge the commit from history.** Filing a public issue describing the leak before rotation makes the problem worse.

## Sensitive data handling

- `.gitignore` excludes `.env`, `.env.*` (except `.env.example`), `*.pem`, `*.key`, `*.crt`, `*.p12`, `.envrc`, `secrets/`, and `private/`.
- Pre-commit hooks reject committing `.env` files explicitly, in case `git add -f` is used by accident.
- Gitleaks runs on every push and PR (see `.github/workflows/secret-scan.yml`).
- See [ADR 0020 — `.env` handling policy](docs/adr/0020-env-handling-policy.md) for the full reasoning.

## Working behind WBG networking

Contributors on WBG networks need a CA bundle configured so HTTPS-dependent commands (git, pip, npm, gh) work behind Zscaler. See [docs/setup/corporate-proxy-and-zscaler.md](docs/setup/corporate-proxy-and-zscaler.md) — that document is marked DRAFT until a colleague verifies it end-to-end on a clean machine.

## Disclosure preference

We follow coordinated disclosure. We will not publicly disclose a vulnerability until a fix or mitigation is available, unless the reporter prefers otherwise.

## Hall of fame

Contributors who report valid issues will be acknowledged in a `SECURITY-CREDITS.md` (created when the first valid report lands), unless they prefer to remain anonymous.
