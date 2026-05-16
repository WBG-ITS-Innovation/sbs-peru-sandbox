---
description: Run the closeout pipeline. Subagents → cross-review → adversarial → deploy test → typed approval gate → session journal → branch + commit + signed push → open PR.
argument-hint: [--dry-run]
---

Close out the current prompt by running the full pipeline.

This command is the keystone. It is the only sanctioned path to a PR.

Steps:

1. Pre-flight:
   - `git status --porcelain` — must show staged changes. If nothing is staged, stop and ask the human what to stage.
   - `git branch --show-current` — note the current branch. If on `main`, the script will create a new branch later. If on a `part-NN/...` branch already, the script will use it.
   - Check `OPENAI_API_KEY` is set. If not, warn and offer to run without cross-review (`--no-cross-review` flag).
   - Check `gh` is authenticated. If not, warn and offer dry-run mode.

2. Run subagent reviews on the staged diff, in order:
   - `reviewer`
   - `architect-guard`
   - `doc-sync`
   - `regulator-readability`
   - `benchmark-checker`
   - Stop here if any return `BLOCK`. Report and exit.

3. Run cross-model review:
   - Invoke `python scripts/cross_review.py --target staged`.
   - The output lands in `docs/reviews/YYYY-MM-DD-<slug>.md`.
   - Read the file. Surface the headline finding to the human.

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
python scripts/close_prompt.py $ARGUMENTS
```

The script implements the steps above. Use `--dry-run` for a no-op rehearsal.
