# Session journal — 2026-05-15 — workflow-harness

- **Date:** 2026-05-15
- **Prompt #:** 01
- **Part:** N/A (cross-cutting harness; precedes Part 1 build work)
- **Branch:** part-01/workflow-harness
- **PR:** _filled in by /close-prompt at the approval gate_
- **Cross-review:** _filled in by /close-prompt; expected path docs/reviews/2026-05-15-staged-diff.md_

## What landed

The project's working agreement, review harness, and governance scaffolding. A fresh contributor can now read [CLAUDE.md](../../CLAUDE.md) in five minutes and understand the bar. The six subagents and eight slash commands are in place. The closeout pipeline (`/close-prompt`) is implemented end-to-end with a non-bypassable typed approval gate before any git push. [docs/PLAN.md](../PLAN.md) is restructured: Parts 1–6 unchanged, new Parts 7–11 added covering Developer Portal + Onboarding (Tier A), Self-Service Onboarding + Per-Institution Ops (Tier B), Production Readiness, AI/ML Evaluation Framework, and Standards Pack & Reporting Taxonomy Distribution. Market research scaffolding is in place at [docs/research/](../research/) with the comparator → PLAN cross-reference map; the substantive `market-comparators.md` file is awaiting paste from the maintainer before this PR is opened.

## Decisions locked

- The six north-star principles are the project's contract: one-command deploy; configuration over code; observability as a first-class feature; standards over inventions plus onboarding as product; plain-language explainability; built on benchmarked precedent. — Codified in [CLAUDE.md](../../CLAUDE.md) — no ADR (these are working principles, not architectural decisions).
- Branch naming convention `part-NN/<slug>` is enforced by a pre-push hook. — Predictable PR mapping to Parts and prompts — no ADR.
- Closeout pipeline is the only sanctioned path to a PR; typed approval gate is non-bypassable; main is protected; no auto-merge. — Prevents auto-push surprises and keeps human-in-the-loop on every change to main — no ADR.
- PLAN.md restructure: Parts 7–11 reflect productisation framing rather than demo framing. — Aligns the build with regulator-grade handoff goals — no ADR; the restructure is captured in a "Plan restructure — 2026-05-15" note inside PLAN.md.

## Decisions deferred (to a named future prompt / part)

- ADR 0001 (MCP + A2A + LangGraph three-layer) — content is deferred to Prompt 9.
- ADR 0002 through 0013 — queued in [docs/adr/README.md](../adr/README.md) with target Part for each.
- ADR 0014 (Dev LLM stack) — flagged for cross-model review with Antoine, target Prompt 6.
- Final license choice — `LICENSE` is a placeholder; the legal review note is in `LICENSE` and will be tracked in `DECISIONS.md` when a path is chosen.
- `gitsign` signed commits — Part 2 finalises the supply-chain story; until then the closeout script commits unsigned with a warning.
- The substantive content of `docs/research/market-comparators.md` — awaiting paste from the maintainer in this same closeout cycle.

## Decisions flagged for cross-model review

- ADR 0014 (Dev LLM stack) — needs Antoine's input on tooling and runtime — target model: cross-review via GPT-5 plus a human review with Antoine — owner: Othman.
- The PLAN.md restructure note itself — flag for the cross-review pass to confirm the redistribution of old Parts 7–10 (specialist agents, frontend, polish) into the new Parts 6+ and 8/9 is coherent, or whether a separate "Specialist Agents" Part should be reintroduced — owner: Othman.

## Subagent verdicts

The six subagents do not yet exist for self-review (this prompt creates them). Verdicts here are the maintainer's manual review against the prompt's "Review (manual for this prompt only)" checklist.

| Subagent | Verdict | Headline finding |
| --- | --- | --- |
| reviewer | APPROVE (manual) | Scope matches prompt; no drive-by changes outside the listed file set. |
| architect-guard | APPROVE (manual) | No locked decisions touched. Stack list in CLAUDE.md mirrors PLAN.md. |
| doc-sync | APPROVE WITH NITS (manual) | `docs/research/market-comparators.md` not yet present; index entries point at it. Resolved in the paste step. |
| regulator-readability | APPROVE (manual) | No AI-tells found on a final pass; `near-real-time` used consistently; no `pilot bank`; no unlabelled benchmarks. |
| benchmark-checker | NOT-APPLICABLE | No ADRs written in this prompt. The subagent itself is wired and ready. |
| second-opinion | WEAKNESS-FLAGGED (manual) | The PLAN.md restructure absorbed Specialist Agents and Frontend Parts without yet specifying where they reappear. Mitigation: tracked in "decisions flagged for cross-review" above; resolved in a follow-up prompt. |

## Cross-model review — triage line

_To be filled in after `/close-prompt` runs `scripts/cross_review.py`. Format: one sentence dispositioning each recommendation as accept / defer / reject._

## Adversarial review — strongest objection

Strongest manual objection: the new Parts 7–11 are productisation-heavy and there is no explicit Part for the specialist agents (Pattern Detection, Institutional Risk, Conduct, Investigation) that drove the demo narrative. Mitigation: deferred — tracked in "decisions flagged for cross-model review" above; a Specialist Agents Part can be reintroduced as Part 6.5 or as extension prompts to Part 6 in the next planning pass.

## Paste-ready block for the maintainer

> Prompt 01 closed. Branch: `part-01/workflow-harness`. PR: <url filled after closeout>. Locked: six north-star principles, branch naming convention, closeout pipeline with typed approval gate, PLAN restructure to Parts 1–6 + new 7–11. Deferred: ADR 0001–0014 content, gitsign signed commits, license choice, market-research substantive content (pasted in this same closeout). Flagged for cross-review: ADR 0014 (Dev LLM stack) and the PLAN restructure absorbing the old Specialist Agents / Frontend Parts. Active Part: cross-cutting — Part 1 begins in Prompt 2 (supply chain & secrets). Next prompt opens with: `/part-start 1` for the Part 1 context dump.

## Notes

- Pre-push hook installed and verified to reject `foo-bar` and accept `part-01/workflow-harness`.
- `python3 -m py_compile scripts/cross_review.py scripts/close_prompt.py` returned clean.
- `CLAUDE.md` is 128 lines (cap is 350).
- A content filter intercepted the inline draft of CODE_OF_CONDUCT.md; the canonical Contributor Covenant 2.1 text is fetched directly from the source as a working step in this same closeout.
- The original docs/PLAN.md had Parts 7–10 (Specialist Agents I/II, Frontend, Polish). Those are reorganised, not abandoned — see the "Plan restructure — 2026-05-15" note inside PLAN.md.

## Mid-prompt correction — 2026-05-16: Azure OpenAI (WBG ITS) replaces personal OpenAI

**What changed.** The cross-review infrastructure originally assumed a personal `openai.com` API key (`OPENAI_API_KEY` / `OPENAI_MODEL`). Mid-closeout, the maintainer corrected the assumption: WBG governance requires Azure OpenAI in the WBG ITS tenancy for any model call touching project content. Personal openai.com keys must not be used on this project.

**Why this matters.** This is a data-governance constraint, not a tooling preference. Routing model calls through a personal account would violate WBG policy and would also misalign the development posture with the likely SBS production posture (Azure tenancy).

**What was actually changed.**

- `scripts/cross_review.py`: switched the client from `openai.OpenAI()` to `openai.AzureOpenAI()`. The script now reads four required env vars — `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION` — and fails loudly with a clear message listing any missing variables. The `model` argument to `chat.completions.create()` is now the deployment **name** (not an OpenAI model id). The `--model` CLI flag was replaced by `--deployment`.
- `scripts/close_prompt.py`: the cross-review gating check no longer looks for `OPENAI_API_KEY`. It now requires all four `AZURE_OPENAI_*` vars to be set before invoking cross-review, and prints a precise skip message when any is missing.
- `.env.example`: rewritten with the four Azure variables and an explanatory header noting that personal openai.com keys are not supported on this project.
- `CLAUDE.md`: replaced both mentions of "OpenAI API" with "Azure OpenAI (via WBG ITS tenancy)". Added a one-line governance note at the top of the pointers section stating that all model calls go through Azure OpenAI for WBG data-governance reasons.
- `docs/CONTRIBUTING.md`: replaced the `OPENAI_API_KEY` reference in the one-time setup block with the four Azure vars. Added a new "Cross-review backend — Azure OpenAI (WBG ITS)" subsection explaining each variable and where to source it.
- `docs/adr/README.md`: added ADR 0015 (`cross-review-llm-backend-azure`) as Proposed, target Prompt 1.5 / Part 2. One-line rationale recorded in the index row.
- Cosmetic nit caught while testing: `_slugify()` previously preserved input file extensions, producing filenames like `2026-05-16-claude.md.md`. Patched to strip a trailing extension; verified via unit-style call on a handful of representative inputs.

**Test run (live, against the WBG-tenanted deployment).** `python3 scripts/cross_review.py --target CLAUDE.md` returned 0 and wrote `docs/reviews/2026-05-16-claude.md.md` (since renamed in subsequent runs to `docs/reviews/2026-05-16-claude.md` per the slugify fix). The review file contains the four model-generated sections plus the auto-appended `## Triage` TODO. The model surfaced real findings, including an ambiguity in `/cross-review`'s "Triage line" vs "Triage section" wording, and a recommendation to add data-classification guidance for what may and may not be submitted to the LLM. Those findings are deferred to a follow-up prompt — they are not in scope for Prompt 01.

**Forward implication.** All cross-review artifacts generated by this project from 2026-05-16 onward are produced via the WBG-governed Azure tenancy. Any contributor without WBG-issued credentials runs `/close-prompt --no-cross-review` and the rest of the pipeline proceeds; cross-reviews can be backfilled later.
