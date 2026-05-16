# ADR 0017 — Dependency update tooling: Dependabot, not Renovate, for Part 1

- **Status:** Accepted
- **Date:** 2026-05-16
- **Target prompt / Part:** Prompt 2 / Part 1
- **Supersedes:** —
- **Superseded by:** —

## Context

The repository needs automated dependency updates from Part 1 onward, because:

- The application stack (Python with uv, Node frontend) lands in later Parts, and Dependabot/Renovate begin watching as soon as a manifest is committed. Configuring this in Part 1 means the noise of "your dependency is N versions behind" never accumulates.
- A regulator-grade handoff requires evidence that dependency hygiene is automated, not "the maintainer remembers to check."

The two practical choices are Dependabot (GitHub-native) and Renovate (third-party, more configurable).

Dependabot:

- GitHub-native, zero configuration to enable, free for public and private repos.
- Supports grouping (introduced in 2023) for minor/patch updates to reduce PR noise.
- Limited cron flexibility (weekly/daily; no arbitrary cron expressions).
- Limited grouping rules compared to Renovate.

Renovate:

- Separate GitHub App; broader ecosystem support.
- Fine-grained grouping, scheduling, auto-merge rules, regex managers.
- Configuration surface area is much larger; the same outcome takes more file to specify.
- Used by some commercial fintech repos and some open-banking implementer repos.

## Decision

Use **Dependabot** for Part 1, with grouping enabled for minor and patch updates on `pip` and `npm`, weekly schedule, Monday 06:00 Europe/Brussels.

`.github/dependabot.yml` covers three ecosystems:

- `github-actions` at `/` — watches workflow `uses:` pins.
- `pip` at `/` — grouped minor+patch; the Python application stack lands in Part 3.
- `npm` at `/frontend` — grouped minor+patch; the Next.js frontend lands in Part 8.

Open-PR cap: 5 per ecosystem. Labels: `dependencies`, `security`. Conventional Commits prefix `chore`.

The docker ecosystem is intentionally absent because no Dockerfiles exist in this prompt. It is added in Part 9 when images land.

Revisit Renovate only if Dependabot's grouping proves insufficient (specifically: if the maintainer is rejecting / re-batching grouped PRs repeatedly because the grouping doesn't match how dependencies cluster in practice). Switching at that point is a small migration.

## Precedent

See [docs/research/supply-chain-precedents.md, §2 — "Dependency update tooling in regulator / government repos"](../research/supply-chain-precedents.md#2-dependency-update-tooling-in-regulator--government-repos). Comparators cited: US 18F (`18F/*`), UK Government Digital Service (`alphagov/*`, including GOV.UK Pay and Notify), UK HMRC (`hmrc/*`), Canada's CDS (`cds-snc/*`), and Singapore GovTech (`opengovsg/*`) all default to Dependabot. The migration pattern (Dependabot first, Renovate only when grouping or scheduling demands exceed it) is documented in that section.

## Divergence

No material divergence. The configuration here matches the prevailing public-sector pattern, with grouping enabled (which is the modern Dependabot default for repos that care about PR noise) and the docker ecosystem deferred to Part 9.

## Consequences

- Every Monday morning a small batch of Dependabot PRs lands. The maintainer triages them in the same review cycle as feature work; CODEOWNERS routes them.
- A `dependencies` and a `security` label are required (see `scripts/bootstrap_github_labels.sh`).
- This ADR will be partially superseded if Renovate is adopted; the supersession will be a new ADR, not a silent edit.

## Flagged for cross-review

None. This is a low-stakes "start with the default and revisit on evidence" call.
