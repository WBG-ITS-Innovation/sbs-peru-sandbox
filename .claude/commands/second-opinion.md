---
description: Run the adversarial second-opinion subagent on a file, glob, or staged diff. Always surfaces at least one concrete weakness.
argument-hint: <path-or-glob-or-staged>
---

Run the `second-opinion` subagent on `$1`.

Steps:

1. If `$1` is `staged`, the target is the output of `git diff --staged`. If it's a path or glob, read each matching file.
2. Read [docs/PLAN.md](docs/PLAN.md), the active Part section, and all "Accepted" ADRs so the subagent has full context.
3. Invoke the `second-opinion` subagent. It must return `WEAKNESS-FLAGGED` with at least one concrete, named weakness — or, rarely, `NO-WEAKNESS-FOUND (explain)` with a clear account of what was looked for and ruled out.
4. Report the verdict, the strongest single objection, and the recommended mitigation to the human inline.

A `NO-WEAKNESS-FOUND` verdict on a substantive design diff is itself a flag — surface it loudly and recommend a human-led review.
