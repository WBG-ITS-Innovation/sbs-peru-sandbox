#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Install local git hooks for this repo.
#
# Currently installed:
#   pre-push — enforces branch naming convention. Allowed patterns:
#     - main
#     - part-NN/<slug>           (prompt work, e.g. part-01/workflow-harness)
#     - docs/<slug>              (documentation-only changes)
#     - fix/<slug>               (bug fixes between prompts)
#     - chore/<slug>             (maintenance, refactoring, tooling)
#     - dependabot/...           (Dependabot automation, any depth)
#
# Run from the repo root:
#   bash scripts/setup_hooks.sh
#
# Re-run to refresh. Idempotent.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="${REPO_ROOT}/.git/hooks"
mkdir -p "${HOOKS_DIR}"

cat > "${HOOKS_DIR}/pre-push" <<'HOOK'
#!/usr/bin/env bash
# Enforce branch naming convention.
#
# Allowed patterns:
#   - main
#   - part-NN/<slug>           (prompt work)
#   - docs/<slug>              (documentation-only)
#   - fix/<slug>               (bug fixes)
#   - chore/<slug>             (maintenance)
#   - dependabot/...           (Dependabot)
#
# This hook runs once per `git push`. It reads refs from stdin in the form
#   <local-ref> <local-sha> <remote-ref> <remote-sha>
# and rejects any push whose local branch name does not match an allowed pattern.

set -euo pipefail

PATTERN='^refs/heads/(main|part-[0-9]{2}/[a-z0-9][a-z0-9-]*|docs/[a-z0-9][a-z0-9-]*|fix/[a-z0-9][a-z0-9-]*|chore/[a-z0-9][a-z0-9-]*|dependabot/.+)$'

bad=0
while read -r local_ref _ _ _; do
  # Deletions look like `(delete)` for local_ref; allow them.
  if [[ "${local_ref}" == "(delete)" ]] || [[ -z "${local_ref}" ]]; then
    continue
  fi
  if [[ ! "${local_ref}" =~ ${PATTERN} ]]; then
    echo "[pre-push] rejected: '${local_ref}' does not match an allowed pattern" >&2
    echo "[pre-push] allowed: main | part-NN/<slug> | docs/<slug> | fix/<slug> | chore/<slug> | dependabot/..." >&2
    echo "[pre-push] examples:" >&2
    echo "[pre-push]   part-02/supply-chain-and-secrets" >&2
    echo "[pre-push]   docs/prompt-01-explainer" >&2
    echo "[pre-push]   fix/cross-review-staging" >&2
    echo "[pre-push]   chore/cleanup-session-journals" >&2
    bad=1
  fi
done

if [[ "${bad}" -ne 0 ]]; then
  echo "[pre-push] rename with: git branch -m <new-name>" >&2
  exit 1
fi

exit 0
HOOK

chmod +x "${HOOKS_DIR}/pre-push"

echo "[setup_hooks] installed ${HOOKS_DIR}/pre-push"
echo "[setup_hooks] allowed branch patterns:"
echo "[setup_hooks]   main"
echo "[setup_hooks]   part-NN/<slug>"
echo "[setup_hooks]   docs/<slug>"
echo "[setup_hooks]   fix/<slug>"
echo "[setup_hooks]   chore/<slug>"
echo "[setup_hooks]   dependabot/..."
