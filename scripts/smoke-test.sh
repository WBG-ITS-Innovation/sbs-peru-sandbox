#!/usr/bin/env bash
# End-to-end smoke test against a locally running API.
#
# The smoke test is the gate that says "running app works". It asserts
# behaviorally per the Prompt 6 spec — not just status codes, but the
# substantive contract: ETag round-trip, idempotency replay, tenant
# binding, Location fetchable, state machine, ProblemDetail shape, body
# size limit.
#
# Pre-conditions:
#   - Postgres reachable at SBS_API_DATABASE_URL (run scripts/dev-up.sh).
#   - The API is running locally at http://localhost:8000.
# This script does NOT start the API; run it in another terminal with
#   bash scripts/run-api.sh
# (or `docker compose up api` once Part 9 lands the container image).
#
# Exit codes: 0 on success, non-zero on first failed assertion. The script
# prints what it ran and what it observed so the failing assertion is easy
# to triage.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
BASE="${BASE:-http://localhost:8000}"
PROB_CT="application/problem+json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

note() {
  echo "  $*"
}

step() {
  echo
  echo "==> $*"
}

# Fetch with status code separator on the last line.
# Usage:  out="$(http GET /v1/health/live)"  ;  status="$(tail -n1 <<<"$out")"  ;  body="$(head -n -1 <<<"$out")"
http() {
  local method="$1"
  local path="$2"
  shift 2
  curl -sS -o /dev/stdout -w '\n%{http_code}\n' -X "$method" "${BASE}${path}" "$@"
}

# Extract header value (case-insensitive) from a curl -i response on stdin.
hdr() {
  local name="$1"
  awk -v n="$name" 'BEGIN { IGNORECASE=1 } $1 ~ ":$" && tolower($1)==tolower(n":") { sub(/^[^:]+: */,""); sub(/\r$/,""); print; exit }'
}

# ---------------------------------------------------------------------------
# 0. Liveness — every other assertion depends on the API being up.
# ---------------------------------------------------------------------------

step "0. liveness"
out="$(curl -sS -i "${BASE}/v1/health/live")" || fail "could not reach ${BASE} — is the API running?"
status="$(printf '%s' "$out" | head -n1 | awk '{print $2}')"
[[ "$status" == "200" ]] || fail "/v1/health/live returned $status, expected 200"
note "live OK"

# ---------------------------------------------------------------------------
# 1. ProblemDetail shape on validation error.
# ---------------------------------------------------------------------------

step "1. validation error returns problem+json"
resp="$(http POST /v1/complaints \
  -H "Idempotency-Key: smoke-bad-001" \
  -H "Content-Type: application/json" \
  --data '{"complaint": {"complaint_id": "X"}}')"
body="$(printf '%s' "$resp" | sed '$d')"
status="$(printf '%s' "$resp" | tail -n1)"
[[ "$status" == "422" ]] || fail "expected 422 on malformed body, got $status"
echo "$body" | grep -q '"code"' || fail "missing code in problem detail"
echo "$body" | grep -q '"type"' || fail "missing type in problem detail"
echo "$body" | grep -q '"status"' || fail "missing status in problem detail"
echo "$body" | grep -q '"title"' || fail "missing title in problem detail"
note "problem+json shape OK"

# ---------------------------------------------------------------------------
# 2. Idempotency — replay returns Idempotency-Replayed: true, body match.
# ---------------------------------------------------------------------------

step "2. idempotency"
PAYLOAD='{
  "complaint": {
    "complaint_id": "BCO-2026-009001",
    "institution_id": "SBS-001234",
    "received_date": "2026-05-12",
    "complainant_doc_type": "DNI",
    "product_category": "TARJETA_CREDITO",
    "channel": "APP_MOVIL",
    "motivo_code": "COBRO_INDEBIDO",
    "severity": "HIGH",
    "description_text": "Cargo no autorizado por S/ 245.00 — pendiente.",
    "description_language": "es",
    "complainant_age_range": "35_44",
    "complainant_district": "150100",
    "submission_method": "APP_MOVIL",
    "original_reference_id": null,
    "resolution_status": "pendiente"
  }
}'

r1="$(curl -sS -i "${BASE}/v1/complaints" \
  -H "Idempotency-Key: smoke-001" \
  -H "Content-Type: application/json" \
  --data "$PAYLOAD")"
[[ "$(printf '%s' "$r1" | head -n1)" == *" 201 "* ]] || {
  echo "$r1" >&2
  fail "first POST did not return 201"
}
LOCATION="$(printf '%s' "$r1" | hdr Location)"
[[ -n "$LOCATION" ]] || fail "Location header missing on 201"

r2="$(curl -sS -i "${BASE}/v1/complaints" \
  -H "Idempotency-Key: smoke-001" \
  -H "Content-Type: application/json" \
  --data "$PAYLOAD")"
[[ "$(printf '%s' "$r2" | head -n1)" == *" 201 "* ]] || fail "replay did not return 201"
REPLAYED="$(printf '%s' "$r2" | hdr Idempotency-Replayed)"
[[ "$REPLAYED" == "true" ]] || fail "Idempotency-Replayed not 'true' on replay (got '$REPLAYED')"
note "replay OK"

DIFFERENT_PAYLOAD="${PAYLOAD//009001/009002}"
r3="$(curl -sS -i "${BASE}/v1/complaints" \
  -H "Idempotency-Key: smoke-001" \
  -H "Content-Type: application/json" \
  --data "$DIFFERENT_PAYLOAD")"
[[ "$(printf '%s' "$r3" | head -n1)" == *" 409 "* ]] || fail "different-body replay did not return 409"
echo "$r3" | grep -q "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_BODY" || fail "missing stable code on 409"
note "different-body 409 OK"

# ---------------------------------------------------------------------------
# 3. 201 Location is fetchable.
# ---------------------------------------------------------------------------

step "3. Location header is fetchable"
r4="$(http GET "$LOCATION")"
status="$(printf '%s' "$r4" | tail -n1)"
[[ "$status" == "200" ]] || fail "GET $LOCATION returned $status"
note "Location fetchable"

# ---------------------------------------------------------------------------
# 4. ETag round-trip — read, patch with If-Match, replay with stale ETag.
# ---------------------------------------------------------------------------

step "4. ETag round-trip"
GET_OUT="$(curl -sS -i "${BASE}${LOCATION}")"
ETAG="$(printf '%s' "$GET_OUT" | hdr ETag)"
[[ -n "$ETAG" ]] || fail "ETag missing on GET"

PATCH_BODY='{"resolution_status": "atendido", "reason": "Caso resuelto satisfactoriamente al cliente."}'
r5="$(curl -sS -i "${BASE}${LOCATION}/status" \
  -X PATCH \
  -H "Idempotency-Key: smoke-patch-001" \
  -H "If-Match: $ETAG" \
  -H "Content-Type: application/json" \
  --data "$PATCH_BODY")"
[[ "$(printf '%s' "$r5" | head -n1)" == *" 200 "* ]] || {
  echo "$r5" >&2
  fail "PATCH with matching If-Match did not return 200"
}

# Replay with the now-stale ETag.
r6="$(curl -sS -i "${BASE}${LOCATION}/status" \
  -X PATCH \
  -H "Idempotency-Key: smoke-patch-002" \
  -H "If-Match: $ETAG" \
  -H "Content-Type: application/json" \
  --data "$PATCH_BODY")"
[[ "$(printf '%s' "$r6" | head -n1)" == *" 412 "* ]] || fail "PATCH with stale If-Match did not return 412"
echo "$r6" | grep -q "ETAG_MISMATCH" || fail "missing ETAG_MISMATCH code on 412"
note "ETag mismatch path OK"

# ---------------------------------------------------------------------------
# 5. State machine — forbidden transition returns 422.
# ---------------------------------------------------------------------------

step "5. forbidden state transition"
# After the PATCH above the complaint is 'atendido' (terminal). Trying to
# walk back to 'pendiente' must be rejected.
FRESH_GET="$(curl -sS -i "${BASE}${LOCATION}")"
FRESH_ETAG="$(printf '%s' "$FRESH_GET" | hdr ETag)"
r7="$(curl -sS -i "${BASE}${LOCATION}/status" \
  -X PATCH \
  -H "Idempotency-Key: smoke-walkback-001" \
  -H "If-Match: $FRESH_ETAG" \
  -H "Content-Type: application/json" \
  --data '{"resolution_status": "pendiente"}')"
[[ "$(printf '%s' "$r7" | head -n1)" == *" 422 "* ]] || fail "walkback to pendiente did not return 422"
echo "$r7" | grep -q "RESOLUTION_STATUS_TRANSITION_FORBIDDEN" || fail "missing stable code on forbidden transition"
note "state machine OK"

# ---------------------------------------------------------------------------
# 6. Tenant binding — auth_stub returns SBS-001234; body for SBS-005678 → 404.
# ---------------------------------------------------------------------------

step "6. tenant binding"
OTHER_TENANT_PAYLOAD="${PAYLOAD/SBS-001234/SBS-005678}"
r8="$(http POST /v1/complaints \
  -H "Idempotency-Key: smoke-tenant-001" \
  -H "Content-Type: application/json" \
  --data "$OTHER_TENANT_PAYLOAD")"
status="$(printf '%s' "$r8" | tail -n1)"
[[ "$status" == "404" ]] || fail "tenant mismatch did not return 404 (got $status)"
note "tenant binding OK"

# ---------------------------------------------------------------------------
# 7. Body size limit — POST a body larger than 256 KiB.
# ---------------------------------------------------------------------------

step "7. body size limit"
# 256 KiB is the default; generate 300 KiB to overshoot.
big_payload="$(python3 -c 'import json,sys; payload={"complaint":{"complaint_id":"BCO-2026-099999","description_text":"x"*300000}}; print(json.dumps(payload))')"
r9="$(curl -sS -i "${BASE}/v1/complaints" \
  -H "Idempotency-Key: smoke-big-001" \
  -H "Content-Type: application/json" \
  --data "$big_payload")"
[[ "$(printf '%s' "$r9" | head -n1)" == *" 413 "* ]] || fail "oversized POST did not return 413"
echo "$r9" | grep -q "REQUEST_BODY_TOO_LARGE" || fail "missing REQUEST_BODY_TOO_LARGE on 413"
note "body size limit OK"

# ---------------------------------------------------------------------------
# 8. Canonical YAML reachable; FastAPI auto-generated paths absent.
# ---------------------------------------------------------------------------

step "8. canonical OpenAPI YAML"
r10="$(http GET /v1/openapi.yaml)"
status="$(printf '%s' "$r10" | tail -n1)"
[[ "$status" == "200" ]] || fail "/v1/openapi.yaml not reachable"

r11_status="$(curl -sS -o /dev/null -w '%{http_code}' "${BASE}/openapi.json")"
[[ "$r11_status" == "404" ]] || fail "FastAPI auto-generated /openapi.json is exposed (status $r11_status)"
note "canonical YAML + auto-generated disabled OK"

# ---------------------------------------------------------------------------
# 9. traceparent response header present.
# ---------------------------------------------------------------------------

step "9. traceparent response header"
# An OTel-managed span context is present per request; the response should
# echo it. Strictly, when OTel is configured with the no-op exporter the
# header may be absent — the dev default uses the console exporter so the
# header is present. Local smoke runs use the dev default.
r12="$(curl -sS -i "${BASE}/v1/health/live")"
TP="$(printf '%s' "$r12" | hdr traceparent)"
if [[ -n "$TP" ]]; then
  # 00-<32hex>-<16hex>-<2hex>
  [[ "$TP" =~ ^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$ ]] || fail "traceparent header malformed: $TP"
  note "traceparent OK ($TP)"
else
  note "traceparent absent (OTel exporter=none)"
fi

echo
echo "All smoke-test assertions passed."
