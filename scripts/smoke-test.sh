#!/usr/bin/env bash
# Auth-free smoke test against a locally running API.
#
# As of Prompt 7 / workstream F.7 the complaint, batch, and institution
# routes require the real auth chain (mTLS + OAuth + HMAC). This script
# exercises only the **unauthenticated** surface that survives that
# migration:
#   - /v1/health/{live,ready,startup}
#   - /v1/openapi.yaml + auto-generated paths disabled
#   - body-size-limit (413 ProblemDetail shape + traceparent / X-Correlation-Id)
#
# For the full signed-request path (mTLS handshake + OAuth token +
# HMAC signature + rate-limit headers + replay rejection), use:
#
#     bash scripts/smoke-test-auth.sh
#
# That script requires the API to be running with
# ``SBS_API_MTLS_MODE=direct SBS_API_AUTH_STUB_ENABLED=false`` and
# the dev CA + oauth client seed in place (one command:
# ``bash scripts/dev-up.sh``).
#
# Pre-conditions for THIS script:
#   - Postgres reachable at SBS_API_DATABASE_URL (run scripts/dev-up.sh).
#   - The API is running locally at http://localhost:8000.
#
# Run with SMOKE_RESET=1 to wipe prior smoke artifacts before starting.
#
# Exit codes: 0 on success, non-zero on first failed assertion.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
BASE="${BASE:-http://localhost:8000}"

SMOKE_RESET="${SMOKE_RESET:-0}"
SUFFIX="$(date +%s)$$"
RUN_ID="smk-${SUFFIX}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

fail() { echo "FAIL: $*" >&2; exit 1; }
note() { echo "  $*"; }
step() { echo; echo "==> $*"; }

http() {
  local method="$1"; local path="$2"; shift 2
  curl -sS -o /dev/stdout -w '\n%{http_code}\n' -X "$method" "${BASE}${path}" "$@"
}

hdr() {
  local name="$1"
  awk -v n="$name" 'BEGIN { IGNORECASE=1 } $1 ~ ":$" && tolower($1)==tolower(n":") { sub(/^[^:]+: */,""); sub(/\r$/,""); print; exit }'
}

if [[ "$SMOKE_RESET" == "1" ]]; then
  echo "==> SMOKE_RESET=1 — wiping prior smoke artifacts"
  if docker ps --format '{{.Names}}' | grep -q '^sbs-postgres$'; then
    docker exec -e PGPASSWORD=sbs -i sbs-postgres \
      psql -U sbs -d sbs_dev -v ON_ERROR_STOP=1 <<'SQL' >/dev/null || true
DELETE FROM idempotency_records WHERE idempotency_key LIKE 'smk-%';
DELETE FROM idempotency_records WHERE idempotency_key LIKE 'smoke-%';
SQL
  fi
fi

# ---------------------------------------------------------------------------
# 0. Liveness — every other assertion depends on the API being up.
# ---------------------------------------------------------------------------

step "0. liveness"
out="$(curl -sS -i "${BASE}/v1/health/live")" || fail "could not reach ${BASE} — is the API running?"
status="$(printf '%s' "$out" | head -n1 | awk '{print $2}')"
[[ "$status" == "200" ]] || fail "/v1/health/live returned $status, expected 200"
note "live OK"

# ---------------------------------------------------------------------------
# 1. ProblemDetail shape on a validation error against the unauth surface.
# ---------------------------------------------------------------------------

step "1. ProblemDetail shape on bad JSON to /v1/oauth/token (auth-free)"
resp="$(http POST /v1/oauth/token \
  -H "Content-Type: application/json" \
  --data 'not-json')"
status="$(printf '%s' "$resp" | tail -n1)"
[[ "$status" == "400" || "$status" == "422" ]] || fail "expected 400/422 on malformed token request, got $status"
body="$(printf '%s' "$resp" | sed '$d')"
echo "$body" | grep -q '"code"' || fail "missing code in problem detail"
echo "$body" | grep -q '"type"' || fail "missing type in problem detail"
note "problem+json shape OK"

# ---------------------------------------------------------------------------
# 2. Body size limit — POST a body larger than 256 KiB at any endpoint.
#    /v1/oauth/token is fine: the body-size middleware runs before any
#    auth so we don't need a real Bearer token.
# ---------------------------------------------------------------------------

step "2. body size limit"
big_payload="$(python3 -c 'print("x" * 300000)')"
r="$(curl -sS -i "${BASE}/v1/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "grant_type=client_credentials&padding=${big_payload}")"
[[ "$(printf '%s' "$r" | head -n1)" == *" 413 "* ]] || fail "oversized POST did not return 413"
echo "$r" | grep -q "REQUEST_BODY_TOO_LARGE" || fail "missing REQUEST_BODY_TOO_LARGE on 413"
# F.2 amendment: 413 carries X-Correlation-Id.
echo "$r" | hdr X-Correlation-Id >/dev/null || fail "413 missing X-Correlation-Id (ADR 0028 F.2 amendment)"
note "body size limit OK (413 + X-Correlation-Id)"

# ---------------------------------------------------------------------------
# 3. Canonical YAML reachable; FastAPI auto-generated paths absent.
# ---------------------------------------------------------------------------

step "3. canonical OpenAPI YAML"
r="$(http GET /v1/openapi.yaml)"
status="$(printf '%s' "$r" | tail -n1)"
[[ "$status" == "200" ]] || fail "/v1/openapi.yaml not reachable"

r_status="$(curl -sS -o /dev/null -w '%{http_code}' "${BASE}/openapi.json")"
[[ "$r_status" == "404" ]] || fail "FastAPI auto-generated /openapi.json is exposed (status $r_status)"
note "canonical YAML + auto-generated disabled OK"

# ---------------------------------------------------------------------------
# 4. traceparent response header present on a 2xx.
# ---------------------------------------------------------------------------

step "4. traceparent response header"
r="$(curl -sS -i "${BASE}/v1/health/live")"
TP="$(printf '%s' "$r" | hdr traceparent)"
if [[ -n "$TP" ]]; then
  [[ "$TP" =~ ^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$ ]] || fail "traceparent header malformed: $TP"
  note "traceparent OK ($TP)"
else
  note "traceparent absent (OTel exporter=none)"
fi

echo
echo "All auth-free smoke-test assertions passed."
echo
echo "==> For the full signed-request path (mTLS + OAuth + HMAC + rate limit),"
echo "    run: bash scripts/smoke-test-auth.sh"
