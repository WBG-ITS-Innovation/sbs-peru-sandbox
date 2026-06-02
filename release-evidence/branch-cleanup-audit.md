# Branch Containment Audit — read-only

**Author:** Track B Salvage agent run on 2026-06-02.
**Reference branches:** `origin/main` (post-Series-1/1b) + `part-14/agent-layer-salvage` (this branch, local-only, not pushed).
**Method:** content-based audit using `git patch-id --stable`. For each remote branch with commits ahead of `main`, compute the patch-id of each unique commit and search for the same patch-id in `(main + part-14)`. The salvaged set is special-cased — its KEEP commits were intentionally transformed by the Series-1c re-scrub, so their patch-ids will not match and the verdict for the parent branch is **SAFE-TO-DELETE** based on content equivalence after transformation, not patch-id equality.
**Output:** classification only. **Nothing is deleted.**

---

## Verdict table

| Remote branch | Ahead of main | Verdict | Rationale |
|---|---:|---|---|
| `origin/chore/series-1-scrub` | 2 | **SAFE-TO-DELETE** | Both commits (`62a4134`, `638061c`) are in main by patch-id (`f7c9081`, `a6af27c` respectively). PR #54 merged. |
| `origin/chore/workshop-day4-backup` | 17 | **SAFE-TO-DELETE** | Tip is `d90c4b4` (RESHAPE frontend). This branch is the workshop backup taken at the same tip as `part-12/agent-layer`. All 17 commits are either (a) in part-14 by content + re-scrub (the 8 KEEPs + the carved eecfdd1), (b) intentionally CUT (`84319dc`, `d90c4b4`, `fcecb44`, `b6406db`, `86b287e`, `6e7220f`), or (c) already in main by content (`cb0e9d1`). Backup record only. |
| `origin/dependabot/github_actions/actions/checkout-6` | 1 | **KEEP** | Active dependabot security PR. Merge separately via the dependabot flow. Never delete dependabot branches without an upstream merge. |
| `origin/dependabot/github_actions/actions/setup-go-6` | 1 | **KEEP** | Same. Active dependabot PR. |
| `origin/dependabot/github_actions/actions/setup-java-5` | 1 | **KEEP** | Same. |
| `origin/dependabot/github_actions/actions/upload-artifact-7` | 1 | **KEEP** | Same. |
| `origin/dependabot/github_actions/astral-sh/setup-uv-7` | 1 | **KEEP** | Same. |
| `origin/part-08/p10-7-ui-polish-final` | 3 | **SAFE-TO-DELETE** | Tip `bf67503 feat(p11): add institution sandbox ingestion client` is an alternate-SHA equivalent of part-12's `834d6e7` (same content, same subject) which IS in part-14 by content. The other two (`a0ca47c`, `cb0e9d1`) are also captured. |
| `origin/part-08/supervisor-ui-backend-wiring` | 1 | **SAFE-TO-DELETE** | `4a97282` matches `2fe701f` on main by patch-id (the supervisor-UI-backend-wiring close commit). |
| `origin/part-09/api-pii-agent-foundation` | 9 | **SAFE-TO-DELETE** | All 9 commits are part-12's keepers (`a0ca47c`, `834d6e7`, `8f28b5a`, `4a5b0e1`, `57f0d4b`, `eecfdd1`, `667b28f`) plus `cb0e9d1`. They are in part-14 by content + re-scrub (or carved, in `eecfdd1`'s case). This branch was an alternate work-in-progress line for the same p11 keeper set. |
| `origin/part-11/institution-real-connection` | 3 | **SAFE-TO-DELETE** | Three commits: `834d6e7`, `a0ca47c`, `cb0e9d1`. All in part-14 by content. |
| `origin/part-12/agent-layer` | 17 | **SAFE-TO-DELETE after part-14 merges** | The original parked branch (drafted PR #53). 8 KEEPs salvaged into part-14 with intentional Series-1c re-scrub; 1 carved (`eecfdd1`); 1 ALREADY-IN-MAIN (`cb0e9d1`); 6 CUT (the 4 demo + 2 RESHAPE per the brief); 1 merge (`3ad0efa`) captured by its linear constituents. PR #53 should be closed (not merged) once part-14 merges, with a pointer comment. See `release-evidence/track-b-triage.md` and `track-b-salvage-findings.md`. |
| `origin/part-13/aggregates-final` | 54 | **KEEP for human review** | Downstream demo/aggregation work built on the part-12 RESHAPE tip. 54 unique commits with subjects clustered as: aggregates (10), p11 (5), demo (5), sandbox (4), red-flags (3), ingestion (3), assistant/chat (3), other (21). Because the parent contains RESHAPE content (six-agent registry, five personas, fraud emergence, DIValeVale, Reclamito, Lupaman) that this salvage explicitly CUT, none of these 54 commits cleanly apply on top of part-14 without re-evaluating the same RESHAPE-vs-locked-architecture question. **A separate triage pass is required before any commit from this branch is salvaged.** Do not delete. |

---

## Summary

| Verdict | Branches | Count |
|---|---|---:|
| SAFE-TO-DELETE | `chore/series-1-scrub`, `chore/workshop-day4-backup`, `part-08/p10-7-ui-polish-final`, `part-08/supervisor-ui-backend-wiring`, `part-09/api-pii-agent-foundation`, `part-11/institution-real-connection`, `part-12/agent-layer` (after part-14 merges) | 7 |
| KEEP (dependabot — never delete; merge via dependabot flow) | 5 dependabot branches | 5 |
| KEEP for human review | `part-13/aggregates-final` (54 commits, downstream of RESHAPE) | 1 |

**Total remote branches inspected:** 13 (excluding `origin/main` and `origin/HEAD`).

---

## Operational notes

1. **Nothing has been deleted by this audit.** The verdict column is advisory. To act on a SAFE-TO-DELETE row, the human runs `git push origin --delete <branch>` after confirming the PR for the merge target is in.
2. The seven SAFE-TO-DELETE branches all have either patch-id matches against `main`/`part-14` or are content-equivalent under the documented Series-1c re-scrub transformation. The audit erred toward "keep" whenever there was ambiguity (the dependabot branches and part-13).
3. `part-13/aggregates-final` is the only branch in the SAFE-vs-KEEP boundary that needs human judgment. It carries demo and aggregate work that may be salvageable in a follow-up pass, but it builds on RESHAPE content that this salvage deliberately abandoned. A second triage report (Track C?) would map its commits the same way `track-b-triage.md` mapped part-12.
4. `chore/workshop-day4-backup` is a label-only backup branch with the same tip as the original `part-12/agent-layer`. It can be deleted in the same operation that retires `part-12/agent-layer` after part-14 merges.

---

*This file lives alongside `track-b-triage.md`, `track-b-salvage-findings.md`, `track-b-salvage-TODO.md`, and the `release-evidence/conflicts/` per-pick deltas.*
