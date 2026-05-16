# ADR 0019 — Dependency-review threshold: fail on `high` and above

- **Status:** Accepted
- **Date:** 2026-05-16
- **Target prompt / Part:** Prompt 2 / Part 1
- **Supersedes:** —
- **Superseded by:** —

## Context

`.github/workflows/dependency-review.yml` runs GitHub's `dependency-review-action` on PRs that touch manifest files (`pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json`, `requirements*.txt`). The action surfaces known-vulnerable dependency updates and blocks the PR if a severity threshold is crossed. The configurable threshold (`fail-on-severity`) takes the values `low`, `moderate`, `high`, or `critical`.

The decision is what threshold to set during the build phase. The tension:

- **Lower threshold (`moderate`)** blocks more PRs. Most blocked-at-moderate findings turn out to be transitive-only, not-applicable-to-our-call-site, or advisories with no patch yet available. A high false-positive rate trains contributors to find the gate's bypass.
- **Higher threshold (`high`)** blocks fewer PRs and lets some real but non-critical vulnerabilities through. The trade-off is that `moderate` findings are still **reported** in the PR comment, so they remain visible — they just don't block.

For a pre-pilot codebase with no production traffic, the right answer is contested. The maintainer flagged this for cross-review.

## Decision

`fail-on-severity: high`.

- **Blocking:** `high` and `critical` findings fail the PR.
- **Reporting (non-blocking):** `moderate` and `low` findings are summarised in the PR comment via `comment-summary-in-pr: on-failure` (the comment fires when a block occurs; lower-severity findings are visible in the action's run log).
- **Revisit:** when the platform enters Part 9 (production readiness) the threshold should drop to `moderate`. That is the right time to absorb the friction — the codebase is then closer to live and the noise floor is better understood.

## Precedent

See [docs/research/supply-chain-precedents.md, §4 — "Dependency-review thresholds"](../research/supply-chain-precedents.md#4-dependency-review-thresholds). Comparators cited: CFPB and UK GDS open-source repositories use `high` as the default block-level during build phases; production-tier projects tighten to `moderate` once the noise floor is understood. The OpenSSF Scorecard "Vulnerabilities" check does not prescribe a threshold but treats `moderate` and above as significant, which is consistent with reporting (not blocking) at moderate.

## Divergence

Some regulator-adjacent repos block at `moderate` from day one. This is defensible when the codebase has production traffic. For a pre-pilot codebase, the false-positive cost outweighs the benefit; SBS adopts `high` now and explicitly schedules the tightening to `moderate` at Part 9. The divergence is the timing of the tightening, not the eventual posture.

## Consequences

- PRs that introduce a `moderate` vulnerable dependency still merge. The reviewer is responsible for noticing the PR comment and judging whether to act.
- A PR that introduces a `high` or `critical` vulnerable dependency cannot merge until the dependency is upgraded, replaced, or the finding is overridden via a tracked exception.
- The action requires `pull-requests: write` to post comments — granted in the workflow file.
- Part 9 will produce a new ADR (or a supersession of this one) when the threshold tightens.

## Flagged for cross-review

Yes. Cross-review owner: Othman. The question for the reviewer is whether `high` is the right block level for a regulator-grade handoff project, or whether tightening to `moderate` should happen sooner than Part 9. Triage line will record the disposition.
