#!/usr/bin/env bash
# Bring up the local-dev Postgres, wait for health, run migrations.
#
# Exit codes:
#   0  ready (DSN printed to stdout on the last line)
#   1  generic failure
#   2  Docker not reachable
#   3  Postgres failed to become healthy within the timeout
#   4  Alembic migration failed

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$REPO_ROOT"

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker is not reachable. Start Docker Desktop and retry." >&2
  exit 2
fi

echo "==> docker compose up -d postgres"
docker compose up -d postgres

echo "==> waiting for postgres to become healthy"
deadline=$(( $(date +%s) + 60 ))
while true; do
  status="$(docker inspect --format '{{.State.Health.Status}}' sbs-postgres 2>/dev/null || echo missing)"
  if [[ "$status" == "healthy" ]]; then break; fi
  if [[ $(date +%s) -ge $deadline ]]; then
    echo "ERROR: postgres did not become healthy within 60s (status=$status)" >&2
    docker compose logs postgres | tail -40 >&2 || true
    exit 3
  fi
  sleep 1
done
echo "    postgres healthy"

DSN="postgresql+asyncpg://sbs:sbs@localhost:5432/sbs_dev" # pragma: allowlist secret

echo "==> alembic upgrade head"
(cd api && SBS_API_DATABASE_URL="$DSN" uv run alembic upgrade head) || {
  echo "ERROR: alembic upgrade head failed" >&2
  exit 4
}

echo
echo "==> ready"
echo "DSN: $DSN"
