---
description: Run the closeout pipeline. Subagents → cross-review → adversarial → deploy test → typed approval gate → session journal → branch + commit + signed push → open PR.
argument-hint: --prompt N --part P --slug <slug> [--dry-run] [--skip-cross-review-with-reason "<reason>"]
---

Close out the current prompt by running the full pipeline.

This command is the keystone. It is the only sanctioned path to a PR.

**Required arguments.** `--prompt N` is mandatory (Prompt-3 carry-over fix #1). The journal filename uses the prompt number directly; the prior regex-from-slug heuristic mis-named Prompt 2's journal and was renamed in PR #17 after the fact. `--part P` and `--slug <slug>` are recommended explicitly; if omitted the script infers them from PLAN.md and the branch name.

Steps:

1. Pre-flight:
   - `git status --porcelain` — must show staged changes. If nothing is staged, stop and ask the human what to stage.
   - `git branch --show-current` — note the current branch. If on `main`, the script will create a new branch later. If on a `part-NN/...` branch already, the script will use it.
   - Check the four `AZURE_OPENAI_*` env vars are set (see [.env.example](../../.env.example)). If any are missing, the script aborts unless `--skip-cross-review-with-reason "<reason>"` is passed. There is no `--no-cross-review` flag.
   - Check `gh` is authenticated. If not, warn and offer dry-run mode.

2. Run subagent reviews on the staged diff, in order:
   - `reviewer`
   - `architect-guard`
   - `doc-sync`
   - `regulator-readability`
   - `benchmark-checker`
   - Stop here if any return `BLOCK`. Report and exit.

3. Run cross-model review:
   - The script invokes `python scripts/cross_review.py --target staged --slug <slug>`. The `--slug` thread-through is Prompt-3 carry-over fix #4 — without it, same-day re-runs all land at `<date>-staged-diff.md` and overwrite each other.
   - The output lands in `docs/reviews/YYYY-MM-DD-<slug>.md`.
   - Read the file. Surface the headline finding to the human.

3b. **Triage-line gate** (Prompt-3 carry-over fix #3). After the cross-review file is written, the closeout refuses to advance to the typed-approval gate if the file's `## Triage` section still contains the literal `_TODO: human-filled` substring. Open the file, disposition each finding above as `accept` / `defer` / `reject` with a one-line reason, save, then re-run `/close-prompt`.

4. Run adversarial review:
   - Invoke the `second-opinion` subagent on the staged diff.
   - Surface the strongest objection inline.

5. Fresh-machine deploy test:
   - Only run if the staged diff touches `infra/`, `helm/`, `terraform/`, `Dockerfile`, `docker-compose*.yml`, or `scripts/setup_*.sh`.
   - If applicable, the script will print the command to run (e.g. `bash scripts/fresh_machine_test.sh`) and pause for the human to run it in a clean environment. The human reports back pass / fail before proceeding.

6. Typed approval gate:
   - Print a single-screen summary: subagent verdicts, cross-review headline, adversarial weakness, files staged, draft commit message, draft branch name, draft PR title and body.
   - Prompt for typed approval. Accepted strings: `approve` or `APPROVE`. Anything else aborts.
   - If `--dry-run` was passed, the script prints the summary and exits 0 without writing the journal or touching git.

7. Write the session journal:
   - Create `docs/sessions/YYYY-MM-DD-prompt-NN-<slug>.md` from `docs/sessions/_template.md`.
   - Fill in locked decisions, deferred decisions, flagged-for-cross-review items, subagent verdicts, cross-review path, adversarial finding.

8. Branch, commit, push:
   - If on `main`, create branch `part-NN/<slug>` (NN inferred from active Part in PLAN.md; slug from the prompt subject).
   - Generate a Conventional Commits message from the staged diff. Format: `<type>: <short description>` plus a body summarising the change. Type is one of `feat`, `fix`, `chore`, `docs`, `refactor`, `test`.
   - Commit. Sign if `gitsign` is configured; otherwise commit unsigned with a warning. (Part 2 will add gitsign; until then, unsigned is acceptable.)
   - Push the branch. The pre-push hook will reject non-conforming branch names.

9. Open PR via `gh pr create`:
   - Title from the commit subject.
   - Body populated from `.github/pull_request_template.md`, with the session journal block, ADRs touched, exit criteria progress, and subagent verdicts filled in.
   - Output the PR URL to the human.

10. Final reminder: main is protected. Do not auto-merge. After CI passes, the human reviews the PR and merges manually via the GitHub UI.

If anything fails between steps 7 and 9, the script does not roll back — it reports what succeeded and stops. The human can resume by running individual git commands.

Invoke the pipeline by calling:

```
uv run python scripts/close_prompt.py $ARGUMENTS
```

Example (Prompt 3): `uv run python scripts/close_prompt.py --prompt 3 --part 1 --slug uv-project-and-python-tooling`.

The script implements the steps above. Use `--dry-run` for a no-op rehearsal.
