#!/usr/bin/env bash
# Tear down the local-dev stack.
#   bash scripts/dev-down.sh        — stop containers, keep the data volume
#   bash scripts/dev-down.sh -v     — also delete the data volume

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$REPO_ROOT"

if [[ "${1:-}" == "-v" ]]; then
  echo "==> docker compose down -v (data volume will be wiped)"
  docker compose down -v
else
  echo "==> docker compose down"
  docker compose down
fi
