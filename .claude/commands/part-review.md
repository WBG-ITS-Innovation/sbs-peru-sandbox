---
description: Run subagent reviews against a Part's exit criteria. Use before closing out a Part.
argument-hint: <part-number>
---

Review the current state of the repo against Part $1's exit criteria from [docs/PLAN.md](docs/PLAN.md).

Run, in this order:

1. Read Part $1's exit criteria from [docs/PLAN.md](docs/PLAN.md).
2. Run the `reviewer` subagent against the diff between `main` and `HEAD`.
3. Run the `architect-guard` subagent against the same diff.
4. Run the `doc-sync` subagent against the same diff.
5. Run the `regulator-readability` subagent against any docs touched.
6. Run the `benchmark-checker` subagent on any ADR or design change in the diff.
7. Run the `second-opinion` subagent last.

Produce a single response with these sections:

- **Exit criteria — met / unmet.** For each bullet in Part $1's exit criteria, mark ✅ / ⏳ / ❌ and cite the evidence (file path / commit).
- **Subagent verdicts.** Verdict and headline finding from each of the six subagents.
- **Blockers.** Any subagent verdict of `BLOCK`, gathered into one list.
- **Recommended next steps.** What needs to land before this Part can close.

If all six subagents return `APPROVE` (or `APPROVE WITH NITS`) and every exit criterion is met, advise the human to run `/close-prompt` and then move to the next Part.
