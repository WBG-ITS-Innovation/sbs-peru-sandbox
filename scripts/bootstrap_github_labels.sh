#!/usr/bin/env bash
# Bootstrap the GitHub labels this repo's tooling and CODEOWNERS rely on.
#
# Idempotent. Re-run safely after a label set changes.
#
# Requires: `gh` authenticated to the repository. Run once per repo (not per
# clone). New contributors do NOT need to run this — only the maintainer at
# first-time-only setup, and again if labels are added later.
#
# Usage:
#   bash scripts/bootstrap_github_labels.sh

set -euo pipefail

# Label definitions. Each row is "<name>|<color-hex-no-hash>|<description>".
# Colours are chosen for legibility on the GitHub label sidebar and do not
# carry meaning beyond "this is the colour we picked".
LABELS=(
  "dependencies|0366d6|Dependency update or related work."
  "security|b60205|Security finding, fix, or related policy work."
  "breaking|d93f0b|Introduces a backwards-incompatible change. Needs an ADR."
  "regulator-readability|fbca04|Flagged by the regulator-readability subagent."
  "architect-guard|5319e7|Flagged by the architect-guard subagent."
  "cross-review-deferred|0e8a16|Cross-model review was deferred and must be backfilled."
  "ci|c5def5|CI configuration or workflow change."
  "python|ededed|Touches Python code or Python deps."
  "javascript|ededed|Touches JS/TS code or Node deps."
  "docker|ededed|Touches Docker / containerisation."
  "good-first-issue|7057ff|Good entry point for a new contributor."
  "needs-adr|c2e0c6|A decision is being made here that requires an ADR."
)

if ! command -v gh >/dev/null 2>&1; then
  echo "[bootstrap_github_labels] 'gh' is not installed or not on PATH." >&2
  echo "[bootstrap_github_labels] install: https://cli.github.com/" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "[bootstrap_github_labels] 'gh' is not authenticated. Run: gh auth login" >&2
  exit 1
fi

for row in "${LABELS[@]}"; do
  IFS="|" read -r name color description <<< "$row"
  echo "[bootstrap_github_labels] upserting label: ${name}"
  # --force makes the create idempotent — it updates colour and description
  # if the label already exists.
  gh label create "${name}" \
    --color "${color}" \
    --description "${description}" \
    --force
done

echo "[bootstrap_github_labels] done. Run \`gh label list\` to verify."
