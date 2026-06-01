# Session journal — reference template

> This file is for human reference only. The closeout pipeline
> (`scripts/close_prompt.py:write_session_journal`) emits a complete journal
> structure inline — it does not read this file. Edit this file to document
> the journal shape; the runtime output is governed by the script.

A session journal documents one closed prompt. It is written by `/close-prompt`
at closeout, then the operator fills in the empty sections before merging the
PR.

## Required sections

- `# Session journal — <YYYY-MM-DD> — <slug>` (H1, exactly one)
- Metadata block (Date, Prompt, Part, Slug, Files touched)
- `## Cross-model review — triage line` (auto-filled by closeout)
- `## Adversarial review` (auto-filled summary or operator-edited)
- `## What landed` (operator: one paragraph, plain language)
- `## Decisions locked` (operator: one line per decision, ADR ref if any)
- `## Decisions deferred (to a named future prompt / part)` (operator: target prompt or Part)
- `## Decisions flagged for cross-model review` (operator: model name and owner)
- `## Subagent verdicts` (operator: one line per subagent run)
- `## Paste-ready block for the maintainer` (auto-templated, operator fills in)
- `## Notes` (operator: anything that doesn't fit elsewhere)

## Style

- Plain language readable by an SBS reviewer (executive), the Superintendent (compliance), the SBS Conduct department head
  (supervisor).
- No AI-tells (leverage, robust, seamless, comprehensive, utilize, etc.).
- Cite ADR numbers when they apply.
- Past tense.
