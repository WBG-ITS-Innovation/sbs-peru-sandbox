# Deferred work

This document tracks decisions and implementations deliberately postponed, with a target Part for revisit. Every entry must have: what was deferred, why, target Part, where the deeper trail lives (issue, ADR, session journal).

Reviewed at the end of each Part. Anything still here at the start of Part 9 (production readiness) is either a Part 9 task or a knowingly-accepted permanent gap.

## Active deferrals

### CI: secret-scanner action vs. binary
- **Status:** Implemented binary-only in PR #7.
- **Why deferred:** `gitleaks-action@v2` requires a paid org license; the binary is free and equivalent for our needs.
- **Open question:** Is the licensed wrapper's value (PR comments, summary reports) worth the cost long-term?
- **Target Part:** 9.
- **Trail:** issue #9, ADR 0016 Amendment 2026-05-16.

### CI: dependency vulnerability scanning
- **Status:** Removed in PR #7.
- **Why deferred:** `dependency-review-action@v4` requires GitHub Advanced Security; not licensed for `WBG-ITS-Innovation` org.
- **Open question:** Procure GHAS, or implement `pip-audit` + `npm audit` workflows ourselves?
- **Target Part:** 9.
- **Trail:** issue #8, ADR 0019 Amendment 2026-05-16.

### Zscaler / corporate-proxy doc verification
- **Status:** `docs/setup/corporate-proxy-and-zscaler.md` marked DRAFT in PR #7.
- **Why deferred:** Requires a WBG colleague to run through it on a clean machine.
- **Target Part:** No specific Part — happens whenever a colleague onboards.
- **Trail:** Doc's own "Open questions" section, Prompt 2 session journal.

### gitsign / signed commits
- **Status:** Closeout warns "gitsign not configured; committing unsigned" each time.
- **Why deferred:** Originally targeted at Part 2; Part 2's current scope is the Data Model & API Skeleton, which is the wrong owner-Part. Re-homed during Prompt 3.
- **Target Part:** To be assigned within Part 1 — owner-prompt picked once tooling (Prompt 4) and Docker Compose (Prompts 5–7) land and the signing-vs-CI dependency surface is clear.
- **Trail:** Prompt 1 journal, Prompt 2 journal, Prompt 3 journal.

### Branch protection: required-approvals set to 0
- **Status:** `main` branch protection has `required_approving_review_count: 0`.
- **Why deferred:** Solo work cannot self-approve. Setting it to 1 today would block every PR.
- **Action needed:** Bump to 1 when a second human joins the repo as a collaborator with review rights.
- **Target:** When Antoine or Fisnik (or any second human reviewer) is added as a collaborator. Not Part-bound; happens at the personnel event.
- **Trail:** This entry.

### Closeout: `--slug` symmetry with `--prompt`
- **Status:** `--slug` is still inferred from the branch name via `infer_slug_from_branch` with a default fallback of `workflow-harness`. `--prompt` was made required in Prompt 3 (carry-over fix #1) but `--slug` was not made symmetric.
- **Why deferred:** Prompt 3's adversarial review surfaced this. The branch-name hook already rejects non-conforming names at push time, so the silent-fallback failure mode is bounded — but it can still emit a wrong slug into the cross-review filename, journal slug field, and PR title if the operator runs from a misnamed branch.
- **Action when triggered:** Either make `--slug` required (matching `--prompt`), or hard-fail when `infer_slug_from_branch` falls back to the default while `--slug` was not supplied. Add a `test_close_prompt_refuses_branch_without_part_prefix` regression test.
- **Target:** Before Prompt 4 closeout.
- **Trail:** Prompt 3 session journal, second-opinion review.

### Cross-review: `enforce_sections` ↔ `check_triage_filled` contract mismatch on `## Triage`
- **Status:** Three sibling bugs in the writer/reader contract between `cross_review.py:enforce_sections` (writer) and `close_prompt.py:check_triage_filled` (reader) on what counts as a `## Triage` heading.
  - **(a) Substring writer vs. line-prefix reader.** The writer injects the placeholder on `"## Triage" in <line>` (substring `in`); the reader picks the LAST `line.startswith("## Triage")` match. The two rules disagree on what a heading is.
  - **(b) `startswith` false positives.** `line.startswith("## Triage")` matches `## Triage rationale`, `## Triage Notes`, `## Triage and disagreements`, or any heading the model invents that begins with the word "Triage". A model that emits both a canonical `## Triage` AND a later `## Triage rationale` defeats the gate: the writer sees the canonical one and injects the marker; the reader's `startswith` matches both and picks the LAST, which may be the rationale section without the marker. Gate green-lights an unreviewed file. Sibling failure: a sufficiently-instructed model emits its own dispositioned `## Triage` section (violating the SYSTEM_PROMPT instruction to leave it blank); writer sees the existing TODO/"fill in" absence and skips the injection.
  - **(c) Byte-offset writer insertion, not line-anchored.** `enforce_sections` does `out = out[:idx] + "## Triage\n\n_TODO..._\n"` where `idx = out.index("## Triage")`. If the substring "## Triage" appears mid-line inside model prose (e.g. an unclosed inline code-span quoting the heading literal), the injected `## Triage` placeholder lands mid-line, not at line-start. The line-anchored reader then correctly reports "no `## Triage` section" — but only because the new section-anchored gate (Prompt 3) catches it. The old whole-file substring check would have silently passed on the malformed file. Surfaced during Prompt 3 closeout against this very PR — Azure (gpt-5.4) truncated mid-sentence while quoting the literal `## Triage` token in its parser-brittleness finding, and `enforce_sections` mangled the injection.
- **Why deferred:** All three siblings surfaced via Prompt 3's adversarial review + the Prompt 3 closeout run itself. The current SYSTEM_PROMPT explicitly tells the model not to fill the Triage section, and (b) requires a model that invents a `## Triage <suffix>` heading. (c) requires a model that quotes `## Triage` mid-prose AND truncates before closing context; today's Azure run hit exactly that. Same class of bug — writer/reader heading-shape contract — so deferring all three to one fix with one shared regression fixture is cheaper than three cascading in-prompt fixes.
- **Action when triggered:** Make writer and reader agree on an exact, case-insensitive, trailing-whitespace-tolerant heading match: `line.rstrip().lower() == "## triage"`. Update both `enforce_sections` (writer) and `_extract_last_triage_section` (reader) to share this rule. In `enforce_sections`, switch from byte-offset insertion (`out[:idx] + ...`) to line-anchored insertion: locate the line whose stripped/lowercased content equals `## triage` and rewrite from that line forward; if no such line exists, append a freshly-anchored `\n\n## Triage\n\n_TODO..._\n` block at EOF. Have `enforce_sections` overwrite the `## Triage` body unconditionally with the placeholder (or wrap any model output with `_TODO: human-filled — model proposed: <verbatim>_`) to close sibling (b). Add one shared regression fixture in `tests/test_close_prompt.py` named `test_triage_writer_reader_contract_handles_heading_shape_drift` covering all three siblings: (i) model emits its own dispositioned `## Triage`; (ii) model quotes `## Triage` mid-sentence inside an inline code span; (iii) heading-shape variants — `## TRIAGE` (case), `## Triage  ` (trailing whitespace), `## Triage rationale` (suffix), `### Triage` (h3 — must not match).
- **Target:** Before Prompt 4 closeout.
- **Trail:** Prompt 3 session journal, second-opinion review. Third sibling surfaced during Prompt 3 closeout — Azure cross-review quoted `## Triage` mid-prose, exercising the malformed-file branch of `check_triage_filled` for the first time.

### ADR 0023 dependency-placement subsection
- **Status:** ADR 0023 documents the workspace layout but does not say which `pyproject.toml` an API-only dependency should land in while members carry `package = false` stubs. A contributor who adds `fastapi` in Part 2 will face an undocumented choice: root `[project.dependencies]`, root `[dependency-groups]`, or `api/pyproject.toml` `[project.dependencies]`.
- **Why deferred:** Prompt 3's adversarial review surfaced this. No real dependency lands until Part 2 / Prompt 4+; documenting before the first real case risks getting the worked example wrong.
- **Action when triggered:** Add a "where do dependencies go before each member has a build backend" subsection to ADR 0023 (or to `docs/setup/uv-quickstart.md`) with a worked example, when the first real dependency lands.
- **Target:** When the first real workspace-member dependency is added (likely Prompt 4 or early Part 2).
- **Trail:** Prompt 3 session journal, second-opinion review.

### ADR 0021 maturity-horizon sentence + `required-version` asymmetry
- **Status:** ADR 0021 says uv is "production-stable through 2025–2026" (three years of public evidence) while the open question is "maintainable in 2028 and beyond" (a five-year horizon). The Divergence section concedes pip-tools as the "documented escape hatch" but does not name the trigger conditions for falling back. Separately, the ADR cites the MCP SDK's `[tool.uv] required-version = ">=0.9.5"` declaration as precedent but explicitly chooses not to declare one for SBS, with the rationale "revisit if version drift causes friction."
- **Why deferred:** Prompt 3's adversarial review surfaced this. Wording-only changes; no behavioural fix needed. The ADR is already Accepted.
- **Action when triggered:** Soften "production-stable through 2025–2026" to its evidentiary base; name explicit re-evaluation triggers (e.g., "Astral pricing/licensing change, `[tool.uv]` table shape change, or Part 9 unconditionally"); add a sentence justifying the `required-version` asymmetry with the MCP precedent.
- **Target:** Next harness-cleanup prompt that touches ADRs (or before Part 9 production readiness).
- **Trail:** Prompt 3 session journal, second-opinion review.

### End-of-Part-1 checkpoint discipline
- **Status:** Commitment recorded; checkpoint to be executed between last Part 1 prompt and first Part 2 prompt.
- **What's deferred:** Running the full seven-category audit established before Prompt 3 (repository structural integrity, documentation consistency, harness functional verification, git history sanity, GitHub repo configuration, carry-over fix verification, cross-check against PLAN.md).
- **Why deferred:** End-of-Part-1 is the right cadence; running it mid-Part would be premature and noisy.
- **Action when triggered:** Run all seven audit categories; commit output to `docs/checkpoints/end-of-part-1.md`; do not start Part 2 until checkpoint is committed.
- **Target:** Between Prompt 8 (Part 1 final) and the first Prompt of Part 2.
- **Trail:** This entry; the audit pattern itself was established in PR #20.

## How to revisit

At the start of Part 9, the planner reads this document top-to-bottom and produces a Part 9 work plan. Items resolved in earlier Parts should be moved to the "Resolved" section below with a one-line note pointing at the resolving PR/commit.

## Resolved

### Real `.secrets.baseline` generation
- **Resolved by:** PR #16, commit `54b7542` (`chore: generate real .secrets.baseline (closes promise from ADR 0016)`).
- **What landed:** Real `detect-secrets` baseline generated against the working tree; the stub is gone.
- **Trail:** ADR 0016, Prompt 2 session journal, PR #16.

### Subagent-verdict table in session-journal template
- **Resolved by:** Prompt 3 (this PR).
- **What landed:** The empty markdown table in `docs/sessions/_template.md` has been replaced with an inline `## Subagent verdicts` heading and a short instruction that the operator writes one line per subagent at closeout. Two prompts of evidence (both with empty tables) did not justify the plumbing for auto-population; revisit if subagent run volume grows.
- **Trail:** Prompt 2 retrospective, Prompt 3 session journal.
