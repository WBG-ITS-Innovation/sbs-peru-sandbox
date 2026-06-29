#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Per-persona curl walkthrough using the dev auth stub (P-RESHAPE-8.6).
#
# Prerequisite: the API must run with BOTH flags set, e.g.
#   SBS_API_AUTH_STUB_ENABLED=true SBS_API_ENVIRONMENT=dev bash scripts/run-api.sh
# Outside dev+flag, a `stub:` token is ignored and these calls 401.
#
# Each call prints the persona, the route, and the EXPECTED status so you
# can eyeball persona scoping. Stub tokens carry the same scope set the
# real JWT path enforces — a 403 here is a real scope denial, not a stub
# shortcut.
set -euo pipefail

BASE="${SBS_API_BASE:-http://localhost:8000}"

# show <persona> <method> <path> <expected> <why>
show() {
  local persona="$1" method="$2" path="$3" expected="$4" why="$5"
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' \
    -X "$method" \
    -H "Authorization: Bearer stub:${persona}" \
    "${BASE}${path}")
  printf '%-8s %-6s %-48s got=%s expect=%s  # %s\n' \
    "$persona" "$method" "$path" "$code" "$expected" "$why"
}

echo "== Jorge (Unit Head) — all patterns + agent monitoring =="
show jorge  GET /v1/internal/cockpit/agents/divalevale/activity 200 "holds agents:read"

echo
echo "== Lucía (Analyst) — complaint detail + agent monitoring =="
show lucia  GET /v1/internal/cockpit/agents/divalevale/activity 200 "holds agents:read"

echo
echo "== María (Supervisor) — pattern landscape =="
show maria  GET /v1/internal/cockpit/agents/divalevale/activity 200 "holds agents:read"

echo
echo "== Rosa (SBS IT) — platform ops only, NO business data =="
show rosa   GET /v1/internal/ops/ingestion_lag                  200 "holds ops:read"
show rosa   GET /v1/internal/exec/cohort_health                 403 "no exec:read"

echo
echo "== Sergio (Superintendent) — exec aggregates only =="
show sergio GET /v1/complaints                                  403 "no institution complaints scope"
show sergio GET /v1/internal/ops/ingestion_lag                  403 "no ops:read"

echo
echo "== Unknown persona — rejected =="
show ghost  GET /v1/internal/cockpit/agents/divalevale/activity 401 "unknown stub persona"
