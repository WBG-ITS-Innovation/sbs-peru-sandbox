# Deferred work

This document tracks decisions and implementations deliberately postponed, with a target Part for revisit. Every entry must have: what was deferred, why, target Part, where the deeper trail lives (issue, ADR, session journal).

Reviewed at the end of each Part. Anything still here at the start of Part 9 (production readiness) is either a Part 9 task or a knowingly-accepted permanent gap.

## Active deferrals

### CI: secret-scanner action vs. binary
- **Status:** Implemented binary-only in PR #7.
- **Why deferred:** `gitleaks-action@v2` requires a paid org license; the binary is free and equivalent for our needs.
- **Open question:** Is the licensed wrapper's value (PR comments, summary reports) worth the cost long-term?
- **Target Part:** 9.
- **Trail:** issue #<TBD>, ADR 0016 Amendment 2026-05-16.

### CI: dependency vulnerability scanning
- **Status:** Removed in PR #7.
- **Why deferred:** `dependency-review-action@v4` requires GitHub Advanced Security; not licensed for `WBG-ITS-Innovation` org.
- **Open question:** Procure GHAS, or implement `pip-audit` + `npm audit` workflows ourselves?
- **Target Part:** 9.
- **Trail:** issue #<TBD>, ADR 0019 Amendment 2026-05-16.

### Real `.secrets.baseline` generation
- **Status:** Stub committed in PR #7.
- **Why deferred:** `detect-secrets` not installed in maintainer's environment at the time.
- **Action needed:** Maintainer runs `detect-secrets scan > .secrets.baseline` locally and commits the real baseline.
- **Target:** Before merging anything further on top of PR #7 — this is short-fuse, not a Part 9 item.
- **Trail:** ADR 0016, Prompt 2 session journal.

### Zscaler / corporate-proxy doc verification
- **Status:** `docs/setup/corporate-proxy-and-zscaler.md` marked DRAFT in PR #7.
- **Why deferred:** Requires a WBG colleague to run through it on a clean machine.
- **Target Part:** No specific Part — happens whenever a colleague onboards.
- **Trail:** Doc's own "Open questions" section, Prompt 2 session journal.

### gitsign / signed commits
- **Status:** Closeout warns "gitsign not configured; committing unsigned" each time.
- **Why deferred:** Scoped as a later Part 1 prompt or Part 2.
- **Target Part:** Part 1 (later prompt) or Part 2.
- **Trail:** Prompt 1 journal, Prompt 2 journal.

## How to revisit

At the start of Part 9, the planner reads this document top-to-bottom and produces a Part 9 work plan. Items resolved in earlier Parts should be moved to the "Resolved" section below with a one-line note pointing at the resolving PR/commit.

## Resolved

_(none yet)_