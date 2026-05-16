#!/usr/bin/env bash
# Install local git hooks for this repo.
#
# Currently installed:
#   pre-push — rejects pushing any branch whose name does not match
#              `part-NN/<slug>` or one of: main.
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
# Enforce branch naming convention: part-NN/<slug> or main.
#
# This hook runs once per `git push`. It reads refs from stdin in the form
#   <local-ref> <local-sha> <remote-ref> <remote-sha>
# and rejects any push whose local branch name does not match the pattern.

set -euo pipefail

PATTERN='^refs/heads/(main|part-[0-9]{2}/[a-z0-9][a-z0-9-]*)$'

bad=0
while read -r local_ref _ _ _; do
  # Deletions look like `(delete)` for local_ref; allow them.
  if [[ "${local_ref}" == "(delete)" ]] || [[ -z "${local_ref}" ]]; then
    continue
  fi
  if [[ ! "${local_ref}" =~ ${PATTERN} ]]; then
    echo "[pre-push] rejected: '${local_ref}' does not match part-NN/<slug>" >&2
    echo "[pre-push] examples: part-01/workflow-harness, part-03/ingestion-tier-1" >&2
    bad=1
  fi
done

if [[ "${bad}" -ne 0 ]]; then
  echo "[pre-push] use: git branch -m part-NN/<slug>; git push -u origin part-NN/<slug>" >&2
  exit 1
fi

exit 0
HOOK

chmod +x "${HOOKS_DIR}/pre-push"

echo "[setup_hooks] installed ${HOOKS_DIR}/pre-push"
echo "[setup_hooks] pattern: refs/heads/(main|part-NN/<slug>)"
