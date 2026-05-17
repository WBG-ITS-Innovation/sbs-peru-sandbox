# Session journal — 2026-05-16 — uv-project-and-python-tooling

- **Date:** 2026-05-16
- **Prompt #:** 3
- **Part:** 1
- **Branch:** part-01/uv-project-and-python-tooling
- **PR:** https://github.com/WBG-ITS-Innovation/sbs-peru-sandbox/pull/22
- **Cross-review:** docs/reviews/2026-05-16-uv-project-and-python-tooling.md (SKIPPED on second invocation; review file from first invocation hand-repaired and preserved)

## What landed

The repository moved from a scripts-only Python layout to a uv-managed workspace. A root `pyproject.toml` declares four members (`api/`, `agents/`, `tools/`, `sdk/`), each with its own stub manifest; `frontend/` and `infra/` carry `.gitkeep` placeholders for Parts 8 and 9. Python 3.12 is pinned via `.python-version`; `uv.lock` is committed. `scripts/requirements-harness.txt` is retired and its three in-tree references are rewritten to use `uv sync`. Three new ADRs land Accepted (0021 uv as package manager, 0022 Python 3.12, 0023 workspace layout); ADR 0020 gains a dated Amendment confirming the `.env` handling policy survives the migration unchanged. Two new research subsections (§6 Python project toolchain, §7 Python version pinning) ground the ADR citations with WebFetch-verified precedents from Astral, FastAPI, the MCP Python SDK, vLLM, Cargo, and pnpm. Three Prompt 1 carry-over fixes land in the closeout harness with regression tests (43 pytest passes): required `--prompt N` argument removes the journal-naming heuristic that mis-named Prompt 2's journal; a section-anchored triage-line gate refuses approval until the operator dispositions cross-review findings; a `--slug` thread-through to `cross_review.py` stops same-day re-runs from overwriting each other. The journal's empty subagent-verdict table is removed; verdicts now go inline as prose.

## Decisions locked

- uv as the Python package manager — ADR 0021. Precedents: Astral first-party self-hosting, FastAPI's Virtual Environments guide, MCP Python SDK's `required-version`.
- Python 3.12 single-version pin, no CI matrix — ADR 0022. Precedents: vLLM, MCP Python SDK, application-vs-library pinning pattern with Pydantic as the library-side counterexample.
- uv workspace with four members (`api/`, `agents/`, `tools/`, `sdk/`), flat per-member layout — ADR 0023. Precedents: uv's own workspaces doc, Astral's uv repo, Cargo workspaces, pnpm workspaces.
- `.env` handling policy holds post-uv migration — ADR 0020 Amendment dated 2026-05-16. `python-dotenv` loads in-script regardless of invocation path.
- `scripts/requirements-harness.txt` retired; harness deps live in root `pyproject.toml` dev group — ADR 0021 clause; logged in `docs/DECISIONS.md`.
- Three closeout harness carry-over fixes: required `--prompt` arg, section-anchored triage-line gate, `--slug` threading. All verified by their own use in this prompt's closeout.

## Decisions deferred (to a named future prompt / part)

- Closeout `--slug` symmetry with `--prompt` — target before Prompt 4 closeout. Branch-name hook bounds the failure mode.
- Writer/reader contract on the `## Triage` heading (three siblings: substring-vs-startswith, false-positive on `## Triage rationale`, byte-offset vs line-anchored insertion in `enforce_sections`) — target before Prompt 4 closeout. One shared regression fixture covers all three.
- ADR 0023 dependency-placement subsection (where dependencies go before each member has a build backend) — target when the first real dependency lands in Part 2 / Prompt 4+.
- ADR 0021 maturity-horizon wording and `required-version` asymmetry — target next harness-cleanup prompt that touches ADRs.
- `deploy-test` false positive on `.gitkeep`-only changes to `infra/` — target Prompt 4 or wherever the regex sees a rewrite.
- Session-journal template duplication into the real journal output (this very file shows the bug — template content concatenated below the real content) — target Prompt 4 closeout harness pass.

## Decisions flagged for cross-model review

- uv maturity for a 2028-and-beyond regulator-grade horizon. Cross-review surfaced two real findings (PLAN.md "structure done" wording, silent `--slug` fallback); both dispositioned DEFER in the triage line. Owner: Othman.

## Subagent verdicts

- `reviewer`: PASS — clean against PLAN Part 1 and the six principles; four minor non-blocking flags (uv-version pin in quickstart, gitsign re-home softness, sdk/ Part-3-vs-Part-7 wording, §6 density).
- `architect-guard`: PASS — three new ADRs land Accepted in the same PR; no locked decision contradicted; DEFERRED.md additions are tightenings or wording-only.
- `doc-sync`: PASS — all six drift checks reconcile.
- `regulator-readability`: PASS — no banned phrasing; one pre-existing nit on PLAN:10 "real-time" flagged for a future doc-sweep.
- `benchmark-checker`: PASS — each ADR cites a specific § of supply-chain-precedents.md, and the sections substantively support the decisions.
- `second-opinion`: WEAKNESS-FLAGGED twice. Round 1: triage-line gate's whole-file substring check was the same brittle-stringy pattern the prompt was retiring. Addressed in-prompt with a section-anchored parser plus three new regression tests. Round 2 (on the updated diff): the new parser still has a writer/reader contract mismatch on the `## Triage` heading shape (substring `in` vs `startswith` vs byte-offset insertion). Deferred to DEFERRED.md as a three-sibling consolidated entry, target before Prompt 4 closeout.

## Cross-model review — triage line

Two surviving findings dispositioned DEFER: PLAN.md "project structure done" wording (the `.gitkeep`-only directories are intentional placeholders per ADR 0023, sharpening tracked for the next PLAN.md-touching prompt) and the silent `--slug` fallback in `close_prompt.py:539` (already tracked in DEFERRED.md, branch-name hook bounds the failure). The third finding (truncated mid-prose in the model's output, on parser brittleness) was caught and addressed in-prompt by the section-anchored gate.

## Adversarial review — strongest objection

Round 1 strongest objection: triage gate's whole-file substring check is the same brittle-stringy heuristic class the slug-regex fix was retiring. Mitigation: in-prompt rewrite to a section-anchored parser, three new regression tests including a meta-review case (the gate marker quoted in `## Summary`). Round 2 strongest objection (on the updated diff): writer/reader still disagree on what counts as a `## Triage` heading. Mitigation: deferred to DEFERRED.md as a three-sibling consolidated entry, target before Prompt 4 closeout; one shared regression fixture will lock the contract.

## Paste-ready block for the maintainer

> Prompt 3 closed. Branch: `part-01/uv-project-and-python-tooling`. PR: https://github.com/WBG-ITS-Innovation/sbs-peru-sandbox/pull/22. Locked: uv as package manager, Python 3.12 single-pin, four-member uv workspace, three closeout harness carry-over fixes (required `--prompt`, section-anchored triage gate, `--slug` threading). Deferred: writer/reader contract on `## Triage` heading (three siblings, Prompt 4); `--slug` symmetry with `--prompt` (Prompt 4); ADR 0023 dependency-placement subsection (when first real dep lands); ADR 0021 maturity wording (next ADR-touching prompt). Flagged for cross-review: uv maturity for 2028+ horizon. Active Part: 1. Next prompt opens with: Prompt 4 — static analysis (ruff + pyright + pre-commit hardening).

## Notes

The closeout ran twice. The first invocation hit Azure OpenAI, wrote a cross-review file, exited at the triage-line gate with a "no `## Triage` section" error — surfacing a third sibling of the writer/reader contract bug in `enforce_sections` (the model emitted `## Triage` inside an unclosed backtick code-span, and the writer's byte-offset insertion placed the canonical heading mid-line rather than at column 0). The reader's new line-anchored parser correctly refused. The file was hand-repaired and the closeout re-invoked with `--skip-cross-review-with-reason` to preserve dispositions. The journal-naming fix and the slug-stability fix were both verified end-to-end by their own use in this closeout: journal filename contains `prompt-03` not `prompt-01`, cross-review filename uses the prompt slug not `staged-diff`. The Claude Code VSCode extension hit three streaming stalls during execution (two in the implementation session, one in the closeout session); each recovered via terminal-side state verification and a fresh chat with a tight resume prompt. The pattern is worth tracking but not currently a blocker.
