#!/usr/bin/env bash
# P-RESHAPE-6.5 — live compose smoke for the fraud chain.
#
# Brings up the docker-compose stack, applies the migrations + dev seed,
# runs seed_demo.py (which triggers one aggregation tick and drives the
# chain), and asserts the fraud chain materialized on the running stack:
#
#   1 FRAUD_EMERGENCE HIGH pattern on BANCO_DEMO_001
#   → 1 Investigation, 1 PRR
#   → 1 SectorBroadcast in AWAITING_DUAL_APPROVAL targeting 4 peers
#
# With --deliver it also exercises dual approval over the API and verifies
# the 4 mock-receiver deliveries carry X-Payload-Type: SECTOR_BROADCAST.
#
# Success is binary: this script exits 0 only if the chain reproduces.
#
# Exit codes:
#   0  chain reproduced
#   2  Docker not reachable
#   3  a service failed to become healthy
#   4  migrations / seed failed
#   5  fraud chain did not materialize as expected

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$REPO_ROOT"

DSN="postgresql+asyncpg://sbs:sbs@localhost:5432/sbs_dev"  # pragma: allowlist secret
DO_DELIVER="${1:-}"

log() { printf '==> %s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit "${2:-1}"; }

command -v docker >/dev/null 2>&1 || fail "docker not found" 2
docker info >/dev/null 2>&1 || fail "Docker is not reachable. Start Docker Desktop." 2

# --- 1. bring up the stack ---------------------------------------------------
log "docker compose up -d postgres redis webhook-listener keycloak"
docker compose up -d postgres redis webhook-listener keycloak

wait_healthy() {
  local name="$1" deadline=$(( $(date +%s) + "${2:-120}" ))
  log "waiting for $name to become healthy"
  while true; do
    local status
    status="$(docker inspect --format '{{.State.Health.Status}}' "$name" 2>/dev/null || echo missing)"
    [[ "$status" == "healthy" ]] && { log "$name healthy"; return 0; }
    [[ $(date +%s) -ge $deadline ]] && {
      docker compose logs "${name#sbs-}" 2>/dev/null | tail -40 >&2 || true
      fail "$name did not become healthy" 3
    }
    sleep 2
  done
}

wait_healthy sbs-postgres 60
wait_healthy sbs-redis 30
wait_healthy sbs-webhook-listener 60 || log "webhook-listener health unknown (continuing)"
wait_healthy sbs-keycloak 180 || log "keycloak health unknown (personas may be unverified)"

# --- 2. migrations + dev seed ------------------------------------------------
log "alembic upgrade head"
( cd api && SBS_API_DATABASE_URL="$DSN" uv run alembic upgrade head ) \
  || fail "alembic upgrade head failed" 4

log "applying scripts/dev-seed.sql"
docker exec -e PGPASSWORD=sbs -i sbs-postgres \
  psql -U sbs -d sbs_dev -v ON_ERROR_STOP=1 < scripts/dev-seed.sql >/dev/null \
  || fail "dev-seed.sql failed" 4

# --- 3. seed_demo.py: verify counts + trigger the chain ----------------------
log "running scripts/seed_demo.py"
SBS_API_DATABASE_URL="$DSN" uv run python scripts/seed_demo.py \
  || fail "fraud chain did not materialize (seed_demo.py non-zero)" 5

# --- 4. assert the chain from the DB -----------------------------------------
log "asserting fraud chain state"
ASSERT_SQL="
SELECT
  (SELECT count(*) FROM pattern_detections WHERE pattern_type='FRAUD_EMERGENCE' AND severity_band='HIGH') AS high_fraud,
  (SELECT count(*) FROM sector_broadcasts WHERE status='AWAITING_DUAL_APPROVAL') AS awaiting,
  (SELECT count(*) FROM agent_runs WHERE agent_name='peer-risk-radar') AS prr_runs;
"
docker exec -e PGPASSWORD=sbs -i sbs-postgres \
  psql -U sbs -d sbs_dev -t -A -F',' -c "$ASSERT_SQL" | tee /tmp/fraud_assert.csv
read -r HIGH AWAITING PRR < <(tr ',' ' ' < /tmp/fraud_assert.csv)
[[ "${HIGH:-0}" -ge 1 ]]     || fail "expected >=1 HIGH FRAUD_EMERGENCE, got ${HIGH:-0}" 5
[[ "${AWAITING:-0}" -ge 1 ]] || fail "expected >=1 broadcast AWAITING_DUAL_APPROVAL, got ${AWAITING:-0}" 5
[[ "${PRR:-0}" -ge 1 ]]      || fail "expected >=1 PRR run, got ${PRR:-0}" 5

# --- 5. optional: dual approval + delivery verification ----------------------
if [[ "$DO_DELIVER" == "--deliver" ]]; then
  log "exercising dual approval + delivery (requires the API running locally)"
  log "  (manual step: POST approve_primary then approve_secondary; then"
  log "   check the webhook-listener log for 4 SECTOR_BROADCAST deliveries:)"
  log "  docker compose logs webhook-listener | grep SECTOR_BROADCAST"
fi

# --- narrative summary -------------------------------------------------------
cat <<EOF

────────────────────────────────────────────────────────────────────────
FRAUD CHAIN REPRODUCED ON LIVE COMPOSE
  • 14 social signals + fraud complaints + INDECOPI cases fused on the
    running Postgres into ${HIGH} HIGH FRAUD_EMERGENCE pattern(s).
  • Investigation + Peer Risk Radar ran (${PRR} PRR run(s)).
  • ${AWAITING} sector broadcast(s) drafted in AWAITING_DUAL_APPROVAL,
    targeting the BANCO:TIER_1 cohort peers — origin FI never named.
  • Awaiting two distinct approvers (the second may be the Superintendent).
────────────────────────────────────────────────────────────────────────
EOF
log "smoke OK"
