---
description: Send a file (or the staged diff) to OpenAI for an independent cross-model critique. Output lands in docs/reviews/.
argument-hint: <path-or-glob>
---

Run a cross-model review of `$1` (a file path, a glob, or the literal string `staged` to mean the staged diff).

Steps:

1. Check that `OPENAI_API_KEY` is set in the environment (or in `.env`). If missing, stop and tell the human to set it.
2. Read `$1`. If it's a glob, concatenate the matched files with clear separators. If it's `staged`, run `git diff --staged` and use that.
3. Call `python scripts/cross_review.py --target "$1"`. The script uses the model from `OPENAI_MODEL` (default `gpt-5`) and writes the critique to `docs/reviews/YYYY-MM-DD-<slug>.md` with five sections:
   - `## Summary`
   - `## Disagreements with primary review`
   - `## Risks not flagged elsewhere`
   - `## Recommended actions`
   - `## Triage` — left blank for the human to fill
4. Report the path of the written review file to the human.
5. Remind the human: the `Triage` line is theirs to fill before `/close-prompt` will accept this review as complete. A cross-review without a triage line is ritual, not signal.

Do not auto-accept or auto-action any of the cross-review's recommendations. The human triages.
