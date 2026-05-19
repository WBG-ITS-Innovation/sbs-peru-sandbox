#!/usr/bin/env bash
# Bring up the local-dev stack — Postgres + Redis + dev CA + OAuth
# clients — so a fresh clone reaches a working signed-request demo in
# one command.
#
# Steps:
#   1. docker compose up -d postgres redis
#   2. Wait for both healthchecks
#   3. alembic upgrade head
#   4. Seed demo institutions + HMAC secrets (scripts/dev-seed.sql)
#   5. scripts/dev-ca.sh (if missing) → dev CA + leaf certs
#   6. Seed institution_certificates from dev-ca/seed-certificates.sql
#   7. scripts/seed-oauth-clients.sh → argon2 hashes for demo clients
#
# Exit codes:
#   0  ready (DSN printed to stdout on the last line)
#   1  generic failure
#   2  Docker not reachable
#   3  Postgres failed to become healthy within the timeout
#   4  Alembic migration failed
#   5  Demo-institution seed failed
#   6  Redis failed to become healthy within the timeout
#   7  dev-ca / OAuth client seed failed

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$REPO_ROOT"

if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker is not reachable. Start Docker Desktop and retry." >&2
  exit 2
fi

echo "==> docker compose up -d postgres redis"
docker compose up -d postgres redis

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

echo "==> waiting for redis to become healthy"
deadline=$(( $(date +%s) + 30 ))
while true; do
  status="$(docker inspect --format '{{.State.Health.Status}}' sbs-redis 2>/dev/null || echo missing)"
  if [[ "$status" == "healthy" ]]; then break; fi
  if [[ $(date +%s) -ge $deadline ]]; then
    echo "ERROR: redis did not become healthy within 30s (status=$status)" >&2
    docker compose logs redis | tail -40 >&2 || true
    exit 6
  fi
  sleep 1
done
echo "    redis healthy"

DSN="postgresql+asyncpg://sbs:sbs@localhost:5432/sbs_dev" # pragma: allowlist secret

echo "==> alembic upgrade head"
(cd api && SBS_API_DATABASE_URL="$DSN" uv run alembic upgrade head) || {
  echo "ERROR: alembic upgrade head failed" >&2
  exit 4
}

echo "==> seeding demo institutions"
docker exec -e PGPASSWORD=sbs -i sbs-postgres \
  psql -U sbs -d sbs_dev -v ON_ERROR_STOP=1 \
  < scripts/dev-seed.sql >/dev/null || {
  echo "ERROR: demo-institution seed failed" >&2
  exit 5
}
echo "    institutions: SBS-001234 (BANCO_DEMO_001), SBS-005678 (COOPAC_DEMO_002)"

if [[ ! -f dev-ca/ca.pem ]]; then
  echo "==> generating dev CA + leaf certs (scripts/dev-ca.sh)"
  bash scripts/dev-ca.sh || {
    echo "ERROR: dev-ca.sh failed" >&2
    exit 7
  }
fi

if [[ -f dev-ca/seed-certificates.sql ]]; then
  echo "==> seeding institution_certificates from dev-ca/seed-certificates.sql"
  docker exec -e PGPASSWORD=sbs -i sbs-postgres \
    psql -U sbs -d sbs_dev -v ON_ERROR_STOP=1 \
    < dev-ca/seed-certificates.sql >/dev/null || {
    echo "ERROR: institution_certificates seed failed" >&2
    exit 5
  }
  echo "    certificate thumbprints loaded (see dev-ca/thumbprints.txt)"
fi

echo "==> seeding oauth_clients (argon2id hashes)"
bash scripts/seed-oauth-clients.sh >/dev/null || {
  echo "ERROR: seed-oauth-clients.sh failed" >&2
  exit 7
}
echo "    oauth_clients: banco-demo-001 (SBS-001234), coopac-demo-002 (SBS-005678)"

echo
echo "==> ready"
echo "DSN: $DSN"
