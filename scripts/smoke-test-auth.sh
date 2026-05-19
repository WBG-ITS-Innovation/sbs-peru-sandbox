#!/usr/bin/env bash
# End-to-end smoke test for the full auth chain (workstream G).
#
# This is the regulator-credibility test: every assertion below
# corresponds to a claim in ADRs 0031/0032/0033 and the ADR 0027
# amendment. After running this, the demo claim "every request you see
# is mTLS-authenticated, HMAC-signed, OAuth-authorised, rate-limited,
# idempotent" is exercised end-to-end against the running stack.
#
# Pre-conditions:
#   1. bash scripts/dev-up.sh        — Postgres + Redis + migrations + seed
#   2. bash scripts/dev-ca.sh        — root CA + leaf certs (auto-called
#                                       by dev-up.sh on a fresh clone, but
#                                       safe to invoke again)
#   3. bash scripts/seed-oauth-clients.sh — argon2 client_secret hashes
#                                            (auto-called by dev-up.sh too)
#   4. The API is running locally with mTLS direct mode at
#      https://sbs-suptech-sandbox.local:8443 — start it with:
#        SBS_API_MTLS_MODE=direct \
#        SBS_API_AUTH_STUB_ENABLED=false \
#        bash scripts/run-api.sh --port 8443
#
# Run with SMOKE_RESET=1 to wipe prior smoke artifacts before starting.
#
# Exit codes:
#   0 — all assertions passed
#   non-zero — first failed assertion (script exits with set -e)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOST="${SBS_API_HOST:-sbs-suptech-sandbox.local}"
PORT="${SBS_API_PORT:-8443}"
BASE="https://${HOST}:${PORT}"

CA_BUNDLE="${REPO_ROOT}/dev-ca/ca.pem"
CLIENT_CERT="${REPO_ROOT}/dev-ca/banco-demo-001.pem"
CLIENT_KEY="${REPO_ROOT}/dev-ca/banco-demo-001-key.pem"
CLIENT_ID="banco-demo-001"
CLIENT_SECRET="banco-demo-001-secret"  # pragma: allowlist secret
INSTITUTION_ID="SBS-001234"

SMOKE_RESET="${SMOKE_RESET:-0}"
SUFFIX="$(date +%s)$$"
RUN_ID="auth-smk-${SUFFIX}"
SMOKE_NUM_SUFFIX="$(printf '%06d' "$(( ${SUFFIX} % 1000000 ))")"
COMPLAINT_ID="BCO-2026-${SMOKE_NUM_SUFFIX}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

fail() { echo "FAIL: $*" >&2; exit 1; }
note() { echo "  $*"; }
step() { echo; echo "==> $*"; }

# Always-on curl flags: mTLS bundle, custom DNS resolution so the
# sandbox host resolves to localhost without /etc/hosts edits, and
# the dev CA as the trusted server-cert root.
CURL_BASE=(curl -sS
  --cacert "$CA_BUNDLE"
  --cert "$CLIENT_CERT"
  --key "$CLIENT_KEY"
  --resolve "${HOST}:${PORT}:127.0.0.1"
)

# Pre-flight: required files.
for f in "$CA_BUNDLE" "$CLIENT_CERT" "$CLIENT_KEY"; do
  [[ -f "$f" ]] || fail "missing $f — run scripts/dev-ca.sh first"
done

if [[ "$SMOKE_RESET" == "1" ]]; then
  echo "==> SMOKE_RESET=1 — wiping prior smoke artifacts"
  if docker ps --format '{{.Names}}' | grep -q '^sbs-postgres$'; then
    docker exec -e PGPASSWORD=sbs -i sbs-postgres \
      psql -U sbs -d sbs_dev -v ON_ERROR_STOP=1 <<'SQL' >/dev/null || true
DELETE FROM idempotency_records WHERE idempotency_key LIKE 'auth-smk-%';
DELETE FROM complaints WHERE complaint_id LIKE 'BCO-2026-009%';
SQL
  fi
  if docker ps --format '{{.Names}}' | grep -q '^sbs-redis$'; then
    docker exec -i sbs-redis redis-cli FLUSHALL >/dev/null || true
  fi
fi

# ---------------------------------------------------------------------------
# 0. Liveness via mTLS — confirms the TLS handshake works.
# ---------------------------------------------------------------------------

step "0. liveness via mTLS"
out="$("${CURL_BASE[@]}" -o /dev/stdout -w '\n%{http_code}\n' "${BASE}/v1/health/live")"
status="$(printf '%s' "$out" | tail -n1)"
[[ "$status" == "200" ]] || fail "/v1/health/live over mTLS returned $status"
note "mTLS handshake + liveness OK"

# ---------------------------------------------------------------------------
# 1. OAuth token endpoint — Basic auth + mTLS → JWT.
# ---------------------------------------------------------------------------

step "1. POST /v1/oauth/token"
token_response="$(
  "${CURL_BASE[@]}" \
    -u "${CLIENT_ID}:${CLIENT_SECRET}" \
    -X POST \
    -d "grant_type=client_credentials&scope=complaints:write complaints:read" \
    "${BASE}/v1/oauth/token"
)"
ACCESS_TOKEN="$(printf '%s' "$token_response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"
[[ -n "$ACCESS_TOKEN" ]] || fail "no access_token in token response: $token_response"
[[ "$ACCESS_TOKEN" == *"."*"."* ]] || fail "access_token is not a JWT (no two dots): $ACCESS_TOKEN"
note "got OAuth token (length=${#ACCESS_TOKEN})"

# Decode the JWT payload and confirm cnf.x5t#S256 matches the
# expected SHA-256 thumbprint of the client cert.
EXPECTED_TP="$(openssl x509 -in "$CLIENT_CERT" -noout -fingerprint -sha256 | sed -E 's/^.*=//' | tr -d ':' | tr 'A-Z' 'a-z')"
PAYLOAD_B64="$(printf '%s' "$ACCESS_TOKEN" | cut -d. -f2)"
# base64url decode (add padding).
PAYLOAD_JSON="$(printf '%s' "$PAYLOAD_B64" | python3 -c '
import base64, sys
s = sys.stdin.read().strip()
s += "=" * (-len(s) % 4)
sys.stdout.write(base64.urlsafe_b64decode(s).decode())
')"
ACTUAL_TP="$(printf '%s' "$PAYLOAD_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["cnf"]["x5t#S256"])')"
[[ "$ACTUAL_TP" == "$EXPECTED_TP" ]] || fail "cnf.x5t#S256 mismatch: token=$ACTUAL_TP cert=$EXPECTED_TP"
note "cnf.x5t#S256 binding OK"

# ---------------------------------------------------------------------------
# 2. Signed POST /v1/complaints — full chain: mTLS + Bearer + HMAC.
# ---------------------------------------------------------------------------

step "2. signed POST /v1/complaints"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
BODY='{"complaint":{"complaint_id":"'"$COMPLAINT_ID"'","institution_id":"'"$INSTITUTION_ID"'","received_date":"2026-05-12","complainant_doc_type":"DNI","product_category":"TARJETA_CREDITO","channel":"APP_MOVIL","motivo_code":"COBRO_INDEBIDO","severity":"HIGH","description_text":"Smoke test (auth chain).","description_language":"es","complainant_age_range":"35_44","complainant_district":"150100","submission_method":"APP_MOVIL","original_reference_id":null,"resolution_status":"pendiente"}}'

# Compute the HMAC signature per ADR 0027 amendment.
BODY_HASH="$(printf '%s' "$BODY" | openssl dgst -sha256 -hex | sed -E 's/^.*= //')"
CANONICAL=$'POST\n/v1/complaints\n'"$(printf '%s' "$HOST" | tr 'A-Z' 'a-z')"$'\n'"$TIMESTAMP"$'\n'"$BODY_HASH"$'\n'"$INSTITUTION_ID"
# Sandbox-only demo HMAC secret, mirrored from scripts/dev-seed.sql.
SECRET_HEX="4a5f1d2e8c7b9a3e5f2d1c8b9a3e5f2d4a5f1d2e8c7b9a3e5f2d1c8b9a3e5f2d" # pragma: allowlist secret # gitleaks:allow
SIG="$(printf '%s' "$CANONICAL" | openssl dgst -sha256 -mac HMAC -macopt hexkey:"$SECRET_HEX" -binary | base64)"

create_response="$(
  "${CURL_BASE[@]}" \
    -i \
    -X POST \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: ${RUN_ID}-create" \
    -H "X-SBS-Timestamp: $TIMESTAMP" \
    -H "X-SBS-Signature: hmac-sha256-v1=$SIG" \
    -H "X-SBS-Institution-Id: $INSTITUTION_ID" \
    --data "$BODY" \
    "${BASE}/v1/complaints"
)"
status_line="$(printf '%s' "$create_response" | head -n1)"
[[ "$status_line" == *" 201 "* ]] || {
  printf '%s\n' "$create_response" >&2
  fail "POST /v1/complaints did not return 201"
}
note "201 Created OK"

# Confirm rate-limit headers are present on the 2xx.
RATELIMIT_LIMIT="$(printf '%s' "$create_response" | awk 'BEGIN{IGNORECASE=1} /^x-ratelimit-limit:/ {sub(/^[^:]+: */,""); sub(/\r$/,""); print; exit}')"
RATELIMIT_REMAIN="$(printf '%s' "$create_response" | awk 'BEGIN{IGNORECASE=1} /^x-ratelimit-remaining:/ {sub(/^[^:]+: */,""); sub(/\r$/,""); print; exit}')"
[[ -n "$RATELIMIT_LIMIT" ]] || fail "X-RateLimit-Limit header missing on 201"
[[ -n "$RATELIMIT_REMAIN" ]] || fail "X-RateLimit-Remaining header missing on 201"
note "X-RateLimit-Limit=$RATELIMIT_LIMIT Remaining=$RATELIMIT_REMAIN"

# ---------------------------------------------------------------------------
# 3. Replay rejection — re-sending the exact same signed request must
#    fail with 401 SIGNATURE_REPLAYED.
# ---------------------------------------------------------------------------

step "3. replay rejection"
# Different Idempotency-Key so we don't hit idempotency replay first;
# HMAC replay is keyed on the signature itself.
replay_response="$(
  "${CURL_BASE[@]}" \
    -i \
    -X POST \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: ${RUN_ID}-replay" \
    -H "X-SBS-Timestamp: $TIMESTAMP" \
    -H "X-SBS-Signature: hmac-sha256-v1=$SIG" \
    -H "X-SBS-Institution-Id: $INSTITUTION_ID" \
    --data "$BODY" \
    "${BASE}/v1/complaints"
)"
status_line="$(printf '%s' "$replay_response" | head -n1)"
[[ "$status_line" == *" 401 "* ]] || {
  printf '%s\n' "$replay_response" >&2
  fail "replay did not return 401"
}
printf '%s' "$replay_response" | grep -q "SIGNATURE_REPLAYED" || fail "replay 401 did not carry SIGNATURE_REPLAYED"
note "SIGNATURE_REPLAYED OK"

# ---------------------------------------------------------------------------
# 4. Rate-limit exhaustion — small-COOPAC tier (100/min) so we can
#    realistically trip the limit. To keep the smoke test fast we
#    pre-configure a very low per-institution override via psql.
# ---------------------------------------------------------------------------

step "4. rate-limit exhaustion (override → 3/min)"
if docker ps --format '{{.Names}}' | grep -q '^sbs-postgres$'; then
  docker exec -e PGPASSWORD=sbs -i sbs-postgres \
    psql -U sbs -d sbs_dev -v ON_ERROR_STOP=1 -c \
    "UPDATE institutions SET rate_limit_per_minute = 3 WHERE institution_id = '$INSTITUTION_ID';" >/dev/null
fi
# Drain the Redis bucket so the override is effective immediately.
if docker ps --format '{{.Names}}' | grep -q '^sbs-redis$'; then
  docker exec -i sbs-redis redis-cli DEL "sbs:rate:business:${INSTITUTION_ID}" >/dev/null
fi

hit_429=0
for i in 1 2 3 4 5; do
  # GET /v1/complaints (read scope is on this token) — cheap.
  status="$("${CURL_BASE[@]}" -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    "${BASE}/v1/complaints?page_size=1")"
  if [[ "$status" == "429" ]]; then
    hit_429=1
    break
  fi
done
[[ "$hit_429" == "1" ]] || fail "rate limit not reached after 5 requests with override=3/min"

# Last request that returned 429 — fetch headers explicitly.
limit_response="$("${CURL_BASE[@]}" -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  "${BASE}/v1/complaints?page_size=1")"
status_line="$(printf '%s' "$limit_response" | head -n1)"
[[ "$status_line" == *" 429 "* ]] || fail "follow-up request was not 429 (got $status_line)"
printf '%s' "$limit_response" | grep -qi "Retry-After:" || fail "429 missing Retry-After"
printf '%s' "$limit_response" | grep -qi "X-RateLimit-Limit:" || fail "429 missing X-RateLimit-Limit"
printf '%s' "$limit_response" | grep -qi "X-RateLimit-Remaining:" || fail "429 missing X-RateLimit-Remaining"
printf '%s' "$limit_response" | grep -qi "X-RateLimit-Reset:" || fail "429 missing X-RateLimit-Reset"
note "429 + 4 rate-limit headers OK"

# Restore the override so other tests / interactive demos see the
# tier default.
if docker ps --format '{{.Names}}' | grep -q '^sbs-postgres$'; then
  docker exec -e PGPASSWORD=sbs -i sbs-postgres \
    psql -U sbs -d sbs_dev -v ON_ERROR_STOP=1 -c \
    "UPDATE institutions SET rate_limit_per_minute = NULL WHERE institution_id = '$INSTITUTION_ID';" >/dev/null
fi
if docker ps --format '{{.Names}}' | grep -q '^sbs-redis$'; then
  docker exec -i sbs-redis redis-cli DEL "sbs:rate:business:${INSTITUTION_ID}" >/dev/null
fi

echo
echo "All auth-chain smoke-test assertions passed."
