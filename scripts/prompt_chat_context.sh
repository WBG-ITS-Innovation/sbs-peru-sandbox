#!/usr/bin/env bash
# Generate the paste-ready context bundle for opening a new prompt chat.
#
# Cold-start chats can't see repo files; they need the current state of key
# project files pasted into the first message. This script assembles that
# bundle from the current main branch.
#
# Usage:
#   bash scripts/prompt_chat_context.sh <part-number>    # prints to stdout
#   bash scripts/prompt_chat_context.sh <part-number> | pbcopy   # macOS: copy to clipboard
#   bash scripts/prompt_chat_context.sh <part-number> | xclip -selection clipboard   # Linux
#
# Example:
#   bash scripts/prompt_chat_context.sh 1 | pbcopy
#   # Then paste into the new Claude Code or Claude.ai chat as the first message.
#
# The principle: cold-start Claude instances need real state, not summarized
# state. Pasting the actual files is the only way to ground them in current
# truth. Don't trust prior-chat memory for anything operational.

set -euo pipefail

PART="${1:-}"
if [[ -z "${PART}" ]]; then
  echo "Usage: $0 <part-number>" >&2
  echo "Example: $0 1   # generates context bundle for a chat working on Part 1" >&2
  exit 1
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"

# Verify we're on main and up to date (best-effort warning, not blocking)
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "${CURRENT_BRANCH}" != "main" ]]; then
  echo "[warn] not on main (currently on ${CURRENT_BRANCH}); bundle reflects this branch's state" >&2
fi

LATEST_SHA="$(git log -1 --format='%H %s')"

cat <<HEADER
SBS Peru sandbox — new prompt chat opener.

Repo: WBG-ITS-Innovation/sbs-peru-sandbox (private)
Predecessor commit on main: ${LATEST_SHA}
Active Part: ${PART}
Working environment: macOS Apple Silicon, WBG VPN with Zscaler SSL inspection,
  Azure OpenAI via WBG ITS for cross-model review.

This is a cold-start chat. The files below are the current state of main as of
the predecessor commit above. Read them before doing anything else. Do not
trust prior-chat memory for operational specifics — use this bundle.

=== CONTEXT BUNDLE ===

--- CLAUDE.md ---
HEADER

if [[ -f CLAUDE.md ]]; then
  cat CLAUDE.md
else
  echo "[missing: CLAUDE.md not found at repo root]"
fi

cat <<MID

--- docs/PLAN.md (Part ${PART} section) ---
MID

if [[ -f docs/PLAN.md ]]; then
  # Extract just the relevant Part section.
  # Match from "### Part N " through to either the next "### Part" or EOF.
  awk -v part="${PART}" '
    BEGIN { in_section = 0 }
    /^### Part / {
      if (in_section) { exit }
      if ($0 ~ "^### Part " part " ") { in_section = 1 }
    }
    in_section { print }
  ' docs/PLAN.md
  # If awk produced nothing, the part header pattern is different — fall back.
  echo ""
  echo "[note: if the section above is empty, check PLAN.md heading format]"
else
  echo "[missing: docs/PLAN.md not found]"
fi

cat <<MID2

--- docs/adr/README.md (ADR queue) ---
MID2

if [[ -f docs/adr/README.md ]]; then
  cat docs/adr/README.md
else
  echo "[missing: docs/adr/README.md not found]"
fi

cat <<MID3

--- Most recent session journal ---
MID3

LATEST_JOURNAL="$(ls -t docs/sessions/*.md 2>/dev/null | grep -v _template | head -1 || true)"
if [[ -n "${LATEST_JOURNAL}" ]]; then
  echo "(${LATEST_JOURNAL})"
  echo ""
  cat "${LATEST_JOURNAL}"
else
  echo "[no session journals found in docs/sessions/]"
fi

cat <<MID4

--- Most recent retrospective (if exists) ---
MID4

LATEST_RETRO="$(ls -t docs/sessions/*retrospective*.md 2>/dev/null | head -1 || true)"
if [[ -n "${LATEST_RETRO}" ]]; then
  echo "(${LATEST_RETRO})"
  echo ""
  cat "${LATEST_RETRO}"
else
  echo "[no retrospective files found — that's expected for routine prompts]"
fi

cat <<FOOTER

=== END CONTEXT BUNDLE ===

Below this line, paste the Prompt N spec, then proceed.
FOOTER
