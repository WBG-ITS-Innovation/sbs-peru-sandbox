# ADR 0016 — Secret-scanner stack

- **Status:** Accepted
- **Date:** 2026-05-16
- **Target prompt / Part:** Prompt 2 / Part 1
- **Supersedes:** —
- **Superseded by:** —

## Context

The repository must reject committed secrets before they reach `main`, and a regulator-grade handoff target (SBS Peru) will inspect the supply-chain controls before relying on the code. There are two practical open-source scanners for this job:

- **gitleaks** — high-confidence pattern matching for known secret shapes (AWS keys, GitHub tokens, Slack tokens, JWTs, certificates, etc.). Low false-positive rate on its native patterns. Runs as a Go binary, fast.
- **detect-secrets** (Yelp) — entropy-based scanning with a committed baseline file (`.secrets.baseline`) that holds the set of "known-and-accepted" findings so the next scan only surfaces new entropy. Higher false-positive rate without a baseline; very effective with one.

The candidate stacks were: (1) gitleaks only, (2) detect-secrets only, (3) both. The maintainer flagged this decision for cross-review because running two scanners has a developer-friction cost that needs justifying.

## Decision

Run **both** scanners locally via pre-commit; run **only gitleaks** in CI.

- `.pre-commit-config.yaml` invokes gitleaks (high-confidence patterns) and detect-secrets (entropy + baseline) on every commit.
- `.github/workflows/secret-scan.yml` invokes gitleaks on every push and pull request. It does not run detect-secrets, because the baseline is a developer aid, not a CI gate. Running detect-secrets in CI without baseline ownership produces noise that pushes contributors to bypass the gate.
- A committed `.secrets.baseline` ships as a stub (because `detect-secrets` is not installed in the maintainer's current environment); the real baseline is generated locally per `docs/CONTRIBUTING.md` and re-committed when it changes materially.

The two-scanner pattern is defense-in-depth: gitleaks catches the shapes attackers actually look for, detect-secrets catches the entropy patterns gitleaks misses (long alphanumeric strings in config files, base64 blobs, ad-hoc tokens). One catches what the other misses, and they overlap on the obvious cases.

## Precedent

See [docs/research/supply-chain-precedents.md, §1 — "Secret-scanner stacks"](../research/supply-chain-precedents.md#1-secret-scanner-stacks). Comparators cited: Yelp `detect-secrets` (the project's published rationale for entropy + baseline), gitleaks usage in `cilium/cilium` and Kubernetes SIG repos, and CFPB open-source repositories running gitleaks in CI. The two-scanner-locally / gitleaks-in-CI pattern is the established default in mature open-source security tooling.

## Divergence

One divergence from precedent:

- **Stub `.secrets.baseline` rather than a real one.** Most repositories that adopt detect-secrets commit a real baseline immediately. This repository commits a documented stub on first introduction because the maintainer's environment does not yet have `detect-secrets` installed and a baseline generated against an empty working tree carries no signal. Contributors generate the real baseline on first clone (see `docs/CONTRIBUTING.md`). This is a transition state, not a steady state.

The CI-runs-only-gitleaks choice is **not** a divergence — it is alignment with the common pattern that supply-chain-precedents.md §1 documents ("both scanners locally, gitleaks-only in CI, detect-secrets baseline committed as a developer aid"). It is recorded in the Decision section above rather than here. A stricter minority pattern (run both in CI) exists; SBS does not adopt it because the local pre-commit hook covers the entropy case for committers who run pre-commit, contributors who bypass pre-commit are caught by gitleaks in CI, and CI noise from entropy false-positives degrades the gate's authority faster than the marginal coverage helps.

## Consequences

- Contributors install `pre-commit` once; the harness setup is documented in `docs/CONTRIBUTING.md`.
- A contributor on a fresh clone who has not run `pre-commit install` is **not** protected locally. CI is still the backstop. This is acceptable because the local hook is a courtesy, not a control; CI is the control.
- The detect-secrets baseline file is sensitive to noise (false positives accepted into it can mask real findings). A reviewer of any change to `.secrets.baseline` should sanity-check the diff.
- This decision is revisited if (a) the developer-friction complaint becomes loud, or (b) a secret leak slips through gitleaks-only CI and would have been caught by detect-secrets in CI.

## Flagged for cross-review

The defense-in-depth claim. Cross-review owner: Othman. Triage line will record whether the marginal coverage of running both scanners locally is worth the friction, or whether one scanner would do.

## Amendment — 2026-05-16

The original Decision specified `gitleaks/gitleaks-action@v2` for CI. On first execution against this PR, the action returned an error: the v2 wrapper requires a commercial gitleaks license for organization-owned repositories, and `WBG-ITS-Innovation` does not have one. The CI workflow has been rewritten to invoke the gitleaks binary directly, which is free and open-source.

The substantive control is unchanged — gitleaks still runs on every push and PR, with the same version pin. Only the wrapper changed.

Follow-up: a paid gitleaks license vs. binary-only CI evaluation is tracked at [issue #9](https://github.com/WBG-ITS-Innovation/sbs-peru-sandbox/issues/9), target Part 9.
