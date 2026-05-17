# ADR 0020 — `.env` handling policy

- **Status:** Accepted
- **Date:** 2026-05-16
- **Target prompt / Part:** Prompt 2 / Part 1
- **Supersedes:** —
- **Superseded by:** —

## Context

The repository needs a single, stated policy for how secrets and per-environment configuration are handled at every stage: developer machine, CI, sandbox, and (eventually) SBS on-prem. Without an explicit policy, the cycle of "commit `.env.local` by accident → rotate → write a one-off rule → repeat" plays out at scale.

Three vectors need coverage:

1. **What never lives in the repository.** Real secrets, real PII, real cryptographic material.
2. **How developers configure their local environment.** A template file plus a sourced-locally `.env`.
3. **How CI configures its environment.** Encrypted secrets in the CI platform's own secret store.

## Decision

The policy:

1. **`.env` and `.env.*` are never committed.** `.env.example` is the only exception and is the source of truth for the variable shape. `.gitignore` enforces this; `.pre-commit-config.yaml` has a `forbid-env-files` hook that catches `git add -f` of a `.env` file.
2. **Real secrets are never in the repository.** Not in code, not in tests, not in docs, not in examples, not in fixtures. The `.env.example` file ships with the *names* of expected variables and explanatory comments, never values.
3. **Developer local `.env`.** Each developer copies `.env.example` to `.env` and fills in real values. The four `AZURE_OPENAI_*` variables are the only mandatory ones at Part 1 (see ADR 0015 for the Azure OpenAI backend decision); more variables join as the application stack lands.
4. **CI secrets.** GitHub Actions secrets store the four `AZURE_OPENAI_*` variables and any future deployment credentials. Secrets are scoped to the workflows that need them; org-level secrets are preferred to repo-level once an organisation owns this repo.
5. **Rotation on exposure.** If a real secret is committed: rotate first, then expunge from history. The order matters — filing a public issue about the leak before rotation increases exposure.
6. **No personal data in repo.** Reproduction cases use the synthetic data generator that ships from Part 4 onward. Real complaint content is out of scope regardless of consent posture; this is a hard rule, not a soft preference.

## Precedent

See [docs/research/supply-chain-precedents.md, §5 — "Environment-variable / secret handling"](../research/supply-chain-precedents.md#5-environment-variable--secret-handling). Comparators cited: the 12-factor app methodology (factor III, "Config") for the `.env`-in-environment, never-in-version-control posture; GitHub's "About secret scanning" and "Managing encrypted secrets in your repository and organization" guidance for the modern CI-side enforcement layer; CFPB, FCA, and HMRC open-source repositories for the established public-sector application of the pattern.

## Divergence

No material divergence. SBS adds explicit per-tool wiring (the Azure OpenAI four-variable shape, WBG ITS tenancy) and an explicit "no personal data in repo" rule that goes beyond what generic 12-factor guidance says, because the regulator-data context warrants it. The mechanics are otherwise standard.

## Consequences

- The `.gitignore` rule `.env.*` is broad and would catch files like `.env.development` if someone created one. The negation `!.env.example` preserves the template. Contributors who want a `.env.staging` (for example) must either rename it or extend the gitignore with a tracked exception, which forces a deliberate choice.
- The `forbid-env-files` pre-commit hook fires on `^\.env($|\.)` and excepts `.env.example`. Contributors who bypass pre-commit (no install, or `--no-verify`) are not protected locally; CI's gitleaks step is the backstop, but it scans for secret-shaped content, not for the literal file name. A `.env` committed with empty values would slip past gitleaks. The defense-in-depth is: gitignore + pre-commit + gitleaks + SECURITY.md disclosure path + the maintainer reading the PR.
- This ADR is the place to point future contributors. SECURITY.md and CONTRIBUTING.md link here.

## Flagged for cross-review

None. This codifies prior decisions and standard practice; no contested design choice.

## Amendment — 2026-05-16

Verified post-uv migration: the policy holds without change. The harness scripts (`scripts/cross_review.py`, `scripts/close_prompt.py`) load `.env` via `python-dotenv` at startup with a script-internal `load_dotenv_if_present()` call, independent of how the script is invoked. The three invocation paths — `python scripts/foo.py`, `uv run python scripts/foo.py`, and direct execution via the shebang — all hit the same `load_dotenv_if_present()` and therefore the same `.env` discovery. `uv run` does not auto-load `.env`; the script's own loader is the only mechanism. No policy change required; this amendment exists to record that the post-migration check was performed.
