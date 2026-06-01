#!/usr/bin/env bash
# Generate a scaffolded draft of the next prompt's spec.
#
# The draft is NOT a final spec — it's the mechanical scaffolding (predecessor
# info, plan section, standard checklist, standard closeout) plus TODO markers
# where strategic shaping is needed (decisions to lock, scope adjustments,
# ADRs to write).
#
# Usage:
#   bash scripts/next_prompt_scaffold.sh <next-prompt-number> <slug>
#
# Example:
#   bash scripts/next_prompt_scaffold.sh 3 uv-project-and-python-tooling
#
# Output: prints draft to stdout. Redirect to a file or pipe to your editor:
#   bash scripts/next_prompt_scaffold.sh 3 uv-project-and-python-tooling > /tmp/prompt-03-draft.md
#
# Or commit it to docs/sessions/ as a draft for review:
#   bash scripts/next_prompt_scaffold.sh 3 uv-project-and-python-tooling > docs/sessions/2026-MM-DD-prompt-03-draft.md
#
# The principle: scaffolding is automated; strategic shaping is not. The TODOs
# in the output are where the human judgment goes. Do not ship a prompt spec
# with TODOs still in it.

set -euo pipefail

PROMPT_N="${1:-}"
SLUG="${2:-}"
if [[ -z "${PROMPT_N}" ]] || [[ -z "${SLUG}" ]]; then
  echo "Usage: $0 <next-prompt-number> <slug>" >&2
  echo "Example: $0 3 uv-project-and-python-tooling" >&2
  exit 1
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"

# Pad prompt number for branch slug (e.g., 3 -> "03")
PROMPT_PADDED="$(printf '%02d' "${PROMPT_N}")"

# Find the active Part for this prompt by scanning PLAN.md.
# Heuristic: look for "Prompt N" mentions in Part sections.
# Fallback: assume current Part is 1 unless overridden via env.
ACTIVE_PART="${ACTIVE_PART:-1}"

LATEST_SHA="$(git log -1 --format='%H' main 2>/dev/null || git log -1 --format='%H')"
LATEST_MSG="$(git log -1 --format='%s' main 2>/dev/null || git log -1 --format='%s')"

# Find the most recent session journal to extract carry-over items.
LATEST_JOURNAL="$(ls -t docs/sessions/*.md 2>/dev/null | grep -v _template | grep -v retrospective | head -1 || true)"
LATEST_RETRO="$(ls -t docs/sessions/*retrospective*.md 2>/dev/null | head -1 || true)"

# Find next available ADR number.
LAST_ADR_NUM="$(grep -oE '^\| 00[0-9]+' docs/adr/README.md 2>/dev/null | grep -oE '[0-9]+' | sort -n | tail -1 || echo "0015")"
NEXT_ADR_NUM=$((10#${LAST_ADR_NUM} + 1))
NEXT_ADR_PADDED="$(printf '%04d' "${NEXT_ADR_NUM}")"

cat <<HEADER
# Prompt ${PROMPT_N} — ${SLUG} (DRAFT — needs strategic shaping)

**Branch:** \`part-${PROMPT_PADDED}/${SLUG}\` *(NOTE: branch slug uses Part number, not Prompt number — verify against PLAN.md)*
**Active Part:** ${ACTIVE_PART} *(VERIFY against PLAN.md)*
**Predecessor:** Prompt $((PROMPT_N - 1)), merged at \`${LATEST_SHA:0:7}\` (\`${LATEST_MSG}\`)
**Closeout:** \`/close-prompt\` with typed approval gate; no auto-merge.

---

## Scope — TODO: strategic shaping needed

The PLAN.md scope for this prompt is auto-included below. **You must:**
- Confirm it's still the right scope (the world may have changed since PLAN.md was written)
- Trim anything that belongs in a later Part
- Adjust for carry-over items from the previous prompt (listed below)
- Adjust for any harness gaps surfaced in the previous prompt

\`\`\`
HEADER

# Extract the relevant Part section from PLAN.md
if [[ -f docs/PLAN.md ]]; then
  awk -v part="${ACTIVE_PART}" '
    BEGIN { in_section = 0 }
    /^### Part / {
      if (in_section) { exit }
      if ($0 ~ "^### Part " part " ") { in_section = 1 }
    }
    in_section { print }
  ' docs/PLAN.md
else
  echo "[missing: docs/PLAN.md not found — manually include Part ${ACTIVE_PART} scope here]"
fi

cat <<MID
\`\`\`

---

## Carry-over items from previous prompt — TODO: review and prioritize

The most recent retrospective and session journal are scanned for items
flagged as "carry-over," "deferred," or "open thread." Review these and
decide which belong in this prompt vs which can wait.

MID

if [[ -n "${LATEST_RETRO}" ]]; then
  echo "Scanning ${LATEST_RETRO}:"
  echo ""
  grep -iE '(carry-over|carryover|deferred|open thread|next prompt|todo|TODO)' "${LATEST_RETRO}" 2>/dev/null | head -20 | sed 's/^/- /' || echo "- [none found in retrospective]"
elif [[ -n "${LATEST_JOURNAL}" ]]; then
  echo "Scanning ${LATEST_JOURNAL}:"
  echo ""
  grep -iE '(carry-over|carryover|deferred|open thread|next prompt|todo|TODO)' "${LATEST_JOURNAL}" 2>/dev/null | head -20 | sed 's/^/- /' || echo "- [none found in journal]"
else
  echo "- [no previous journal or retrospective found]"
fi

cat <<MID2

---

## Deliverables — TODO: list new files and modified files

### New files
- TODO

### Modified files
- TODO

---

## Decisions to lock (ADRs) — TODO: strategic shaping required

Each decision this prompt locks needs an ADR. ADRs are marked **Accepted** on
merge and **must cite at least one named precedent**. First-principles-only
ADRs are rejected by the benchmark-checker subagent.

Next available ADR number: **${NEXT_ADR_PADDED}**.

- **ADR ${NEXT_ADR_PADDED} — TODO: title.** TODO: decision summary. Precedent: TODO.
- **ADR $(printf '%04d' $((NEXT_ADR_NUM + 1))) — TODO: title.** TODO: decision summary. Precedent: TODO.
- (add as many as this prompt locks)

---

## Decisions to defer — TODO: list deferred items

- TODO

---

## Decisions flagged for cross-model review — TODO

Decisions where you'd want the cross-review backend (Azure OpenAI via WBG) to
push back. Owner: Othman (or whoever should adjudicate).

- TODO

---

## Subagent review checklist (standard)

| Subagent | What it must check |
| --- | --- |
| reviewer | Only listed files touched. No drive-by changes. |
| architect-guard | No locked decision from previous prompts is reopened. ADRs added in this prompt land as Accepted in the same commit. |
| doc-sync | New files linked from README.md, CLAUDE.md, or CONTRIBUTING.md as appropriate. New ADRs appear in docs/adr/README.md. |
| regulator-readability | No AI-tells. Plain-language ADR summaries. Documents readable by non-engineer reviewers (the SBS Conduct department head, the Superintendent, an SBS reviewer). No unlabelled benchmarks. |
| benchmark-checker | Each ADR cites at least one named precedent. Reject first-principles-only ADRs. |
| second-opinion | Strongest objection logged in journal under "Adversarial review"; mitigation named or deferred to tracked follow-up. |

---

## Closeout (standard)

Run \`/close-prompt --prompt ${PROMPT_N} --part ${ACTIVE_PART} --slug ${SLUG}\`.
\`--prompt\` is required (Prompt-3 carry-over fix #1: the journal filename
uses the prompt number directly, no slug-regex heuristic). The typed approval
gate is non-bypassable. The closeout commit must include the cross-review
file under \`docs/reviews/<date>-${SLUG}.md\` (slug threaded via
\`cross_review.py --slug\`, Prompt-3 carry-over fix #4). The triage-line gate
will refuse the typed-approval prompt until the cross-review's \`## Triage\`
section's \`_TODO: human-filled\` placeholder is replaced with
\`accept\` / \`defer\` / \`reject\` per finding (Prompt-3 carry-over fix #3).
If cross-review can't run (Zscaler / Azure creds), use
\`--skip-cross-review-with-reason "<reason>"\` and verify the skip line
lands in the journal. Paste-ready block lands in
\`docs/sessions/<date>-prompt-${PROMPT_PADDED}-${SLUG}.md\`, matching the
established naming pattern.

---

## END DRAFT — strip this line before pasting to Claude Code

Items marked **TODO** must be filled in by a human before this prompt is
executable. The mechanical scaffolding above is correct; the strategic
shaping is your work.
