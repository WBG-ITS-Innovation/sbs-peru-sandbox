#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Sandbox-scale performance smoke — sustained signed Tier-1 submissions.
#
# ---------------------------------------------------------------------------
# THIS IS NOT A LOAD TEST.
# ---------------------------------------------------------------------------
# It drives a modest, fixed request rate at a developer-machine sandbox for
# one minute and reports what came back. It is useful for one thing: noticing
# that a change made the ingest path dramatically slower. It establishes
# nothing about production capacity.
#
# It is not a load test because: the client, the API, Postgres and Redis all
# share one machine and compete for the same cores; the database holds sandbox
# volumes, so every index is small and every query is cheap; there is exactly
# one API process rather than a replica set behind a load balancer; requests
# come from one client with one certificate, so per-institution rate limiting
# and connection pooling are never stressed; and a 60-second window is far too
# short for GC, connection churn, or cache eviction to show up.
#
# A real load test — at your projected peak, on production-shaped
# infrastructure, with your data volumes — is a go-live gate. See
# docs/OPERATOR-CHECKLIST.md.
#
# What it measures: end-to-end wall-clock latency of a signed
# POST /v1/complaints, from the client, including TLS handshake, OAuth bearer
# validation, HMAC verification, idempotency, and the synchronous part of
# ingestion. The agent pipeline runs off the request path, so its cost is not
# in these numbers.
#
# Pre-conditions — the same stack scripts/smoke-test-auth.sh needs:
#   1. bash scripts/dev-up.sh
#   2. The institution-facing API on :8443 with the real auth chain:
#        SBS_API_MTLS_MODE=direct \
#        SBS_API_AUTH_STUB_ENABLED=false \
#        SBS_API_PORT=8443 \
#        bash scripts/run-api.sh
#
# Usage:
#   bash scripts/perf-smoke.sh                 # 20 rps for 60s
#   PERF_RPS=10 PERF_DURATION=30 bash scripts/perf-smoke.sh
#   PERF_JSON=out.json bash scripts/perf-smoke.sh
#
# Exit codes:
#   0 — the run completed (this says nothing about whether the numbers are good)
#   1 — pre-flight failure, or the error rate exceeded PERF_MAX_ERROR_RATE
#
# No new dependencies: bash, curl, openssl, and python3, all of which the
# existing smoke scripts already require.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$REPO_ROOT"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOST="${SBS_API_HOST:-sbs-suptech-sandbox.local}"
PORT="${SBS_API_PORT:-8443}"
BASE="https://${HOST}:${PORT}"
HOST_HEADER="${HOST}:${PORT}"

CA_BUNDLE="${REPO_ROOT}/dev-ca/ca.pem"
CLIENT_CERT="${REPO_ROOT}/dev-ca/banco-demo-001.pem"
CLIENT_KEY="${REPO_ROOT}/dev-ca/banco-demo-001-key.pem"
CLIENT_ID="banco-demo-001"
CLIENT_SECRET="banco-demo-001-secret"  # pragma: allowlist secret
INSTITUTION_ID="SBS-001234"

# Sandbox-only demo HMAC secret, mirrored from scripts/dev-seed.sql.
SECRET_HEX="4a5f1d2e8c7b9a3e5f2d1c8b9a3e5f2d4a5f1d2e8c7b9a3e5f2d1c8b9a3e5f2d" # pragma: allowlist secret # gitleaks:allow

PERF_RPS="${PERF_RPS:-20}"
PERF_DURATION="${PERF_DURATION:-60}"
PERF_MAX_ERROR_RATE="${PERF_MAX_ERROR_RATE:-1.0}"   # percent
PERF_JSON="${PERF_JSON:-}"

fail() { echo "FAIL: $*" >&2; exit 1; }
note() { echo "  $*"; }
step() { echo; echo "==> $*"; }

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT
RESULTS="${WORK_DIR}/results.txt"
: > "$RESULTS"

CURL_BASE=(curl -sS
  --cacert "$CA_BUNDLE"
  --cert "$CLIENT_CERT"
  --key "$CLIENT_KEY"
  --resolve "${HOST}:${PORT}:127.0.0.1"
)

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

step "pre-flight"

for f in "$CA_BUNDLE" "$CLIENT_CERT" "$CLIENT_KEY"; do
  [[ -f "$f" ]] || fail "missing $f — run scripts/dev-ca.sh first"
done
command -v openssl >/dev/null || fail "openssl not found"
command -v python3 >/dev/null || fail "python3 not found"

health="$("${CURL_BASE[@]}" -o /dev/null -w '%{http_code}' "${BASE}/v1/health/live" || true)"
[[ "$health" == "200" ]] || fail "API not reachable at ${BASE} (health returned '${health}') — start the :8443 process, see the header of this script"
note "API healthy at ${BASE}"

TOTAL_REQUESTS=$(( PERF_RPS * PERF_DURATION ))
note "plan: ${PERF_RPS} rps for ${PERF_DURATION}s = ${TOTAL_REQUESTS} signed POST /v1/complaints"

# ---------------------------------------------------------------------------
# OAuth token — acquired once and reused for the whole run.
#
# Deliberate: the token endpoint is separately rate-limited
# (SBS_API_RATE_LIMIT_TOKEN_ENDPOINT_PER_MINUTE), so re-acquiring per request
# would measure that limiter rather than the ingest path.
# ---------------------------------------------------------------------------

step "acquiring OAuth token"

token_response="$(
  "${CURL_BASE[@]}" \
    -X POST \
    -u "${CLIENT_ID}:${CLIENT_SECRET}" \
    -d 'grant_type=client_credentials' \
    "${BASE}/v1/oauth/token"
)"
ACCESS_TOKEN="$(printf '%s' "$token_response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')" \
  || fail "no access_token in token response: $token_response"
note "token acquired (length=${#ACCESS_TOKEN})"

# ---------------------------------------------------------------------------
# One signed request. Backgrounded by the driver loop below.
#
# Each request needs a unique complaint_id and Idempotency-Key: a repeated
# idempotency key returns the cached first response, which would measure the
# idempotency store rather than ingestion.
# ---------------------------------------------------------------------------

RUN_EPOCH="$(date +%s)"
RUN_TAG="perf-${RUN_EPOCH}$$"

# Complaint ids must be unique across runs, not merely within one. The id
# space is six digits (BCO-2026-NNNNNN, the convention scripts/smoke-test-auth.sh
# uses), so each run takes a base offset from the clock and walks forward from
# there. Re-running with a fixed base collided with the previous run's rows and
# returned 409 Conflict for exactly as many requests as the shorter run had
# made — which looked like an error-rate finding and was an artefact.
RUN_ID_BASE="$(( (RUN_EPOCH + $$) % 1000000 ))"

send_one() {
  local seq="$1"
  local complaint_id timestamp body body_hash canonical sig out code total

  complaint_id="$(printf 'BCO-2026-%06d' "$(( (RUN_ID_BASE + seq) % 1000000 ))")"
  timestamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  body='{"complaint":{"complaint_id":"'"$complaint_id"'","institution_id":"'"$INSTITUTION_ID"'","received_date":"2026-05-12","complainant_doc_type":"DNI","product_category":"TARJETA_CREDITO","channel":"APP_MOVIL","motivo_code":"COBRO_INDEBIDO","severity":"HIGH","description_text":"Perf smoke (sandbox-scale, not a load test).","description_language":"es","complainant_age_range":"35_44","complainant_district":"150100","submission_method":"APP_MOVIL","original_reference_id":null,"resolution_status":"pendiente"}}'

  body_hash="$(printf '%s' "$body" | openssl dgst -sha256 -hex | sed -E 's/^.*= //')"
  canonical=$'POST\n/v1/complaints\n'"$(printf '%s' "$HOST_HEADER" | tr 'A-Z' 'a-z')"$'\n'"$timestamp"$'\n'"$body_hash"$'\n'"$INSTITUTION_ID"
  sig="$(printf '%s' "$canonical" | openssl dgst -sha256 -mac HMAC -macopt hexkey:"$SECRET_HEX" -binary | base64)"

  # %{http_code} and %{time_total}, nothing else on stdout.
  out="$(
    "${CURL_BASE[@]}" \
      -o /dev/null \
      -w '%{http_code} %{time_total}' \
      -X POST \
      -H "Authorization: Bearer $ACCESS_TOKEN" \
      -H "Content-Type: application/json" \
      -H "Idempotency-Key: ${RUN_TAG}-${seq}" \
      -H "X-SBS-Timestamp: $timestamp" \
      -H "X-SBS-Signature: hmac-sha256-v1=$sig" \
      -H "X-SBS-Institution-Id: $INSTITUTION_ID" \
      --data "$body" \
      "${BASE}/v1/complaints" 2>/dev/null
  )" || out="000 0"

  code="${out%% *}"
  total="${out##* }"
  printf '%s %s\n' "$code" "$total" >> "$RESULTS"
}

# ---------------------------------------------------------------------------
# Driver — open-loop, one wave per second.
#
# Each second launches PERF_RPS requests in the background and then sleeps
# until the next second boundary, so offered load stays at the target rate
# regardless of how slow responses get. That is the honest shape for a rate
# claim: a closed-loop driver would silently reduce its own rate as latency
# rose and report a rate that was never offered.
#
# The arrival process is per-second batches, not a smooth or Poisson one.
# Sub-second burstiness in the numbers is an artefact of that, and is one more
# reason these figures are indicative only.
# ---------------------------------------------------------------------------

step "running — ${PERF_RPS} rps for ${PERF_DURATION}s"

# Sub-second clock. `date +%s` is whole seconds, and pacing a one-second wave
# with a one-second-resolution clock produces spurious "behind schedule"
# readings — a wave starting at x.9 and ending at y.0 measures as a full
# second. python3 is already required, so use a float clock.
now() { python3 -c 'import time; print(time.time())'; }

WALL_START_F="$(now)"
WALL_START="$(date +%s)"
seq_no=0
behind_waves=0

for (( second = 0; second < PERF_DURATION; second++ )); do
  for (( i = 0; i < PERF_RPS; i++ )); do
    seq_no=$(( seq_no + 1 ))
    send_one "$seq_no" &
  done

  # Sleep until this wave's absolute deadline rather than for a fixed
  # interval, so dispatch cost does not accumulate as drift across the run.
  # A wave that misses its own deadline means dispatch alone could not keep
  # up with the offered rate — the client, not the server, is the bottleneck,
  # and the run is no longer testing what it claims to.
  read -r remaining behind <<<"$(
    WAVE_INDEX="$second" WALL_START_F="$WALL_START_F" python3 -c '
import os, time
deadline = float(os.environ["WALL_START_F"]) + int(os.environ["WAVE_INDEX"]) + 1
remaining = deadline - time.time()
print(f"{max(0.0, remaining):.3f}", "1" if remaining < 0 else "0")
'
  )"
  if [[ "$behind" == "1" ]]; then
    behind_waves=$(( behind_waves + 1 ))
  else
    sleep "$remaining"
  fi

  if (( (second + 1) % 10 == 0 )); then
    note "$(( second + 1 ))/${PERF_DURATION}s elapsed, ${seq_no} dispatched"
  fi
done

if (( behind_waves > 0 )); then
  note "WARNING: ${behind_waves}/${PERF_DURATION} waves missed their dispatch deadline —"
  note "         the client could not offer the target rate, so treat the rate as unmet"
fi

note "waiting for in-flight requests to drain"
wait
WALL_END="$(date +%s)"
WALL_SECONDS=$(( WALL_END - WALL_START ))

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

step "results"

PERF_RPS="$PERF_RPS" \
PERF_DURATION="$PERF_DURATION" \
PERF_MAX_ERROR_RATE="$PERF_MAX_ERROR_RATE" \
PERF_JSON="$PERF_JSON" \
WALL_SECONDS="$WALL_SECONDS" \
python3 - "$RESULTS" <<'PY'
import collections, json, os, sys

path = sys.argv[1]
rows = []
with open(path) as fh:
    for line in fh:
        parts = line.split()
        if len(parts) != 2:
            continue
        code, total = parts
        try:
            rows.append((code, float(total)))
        except ValueError:
            continue

if not rows:
    print("  no results recorded — nothing to report")
    sys.exit(1)

target_rps = int(os.environ["PERF_RPS"])
duration = int(os.environ["PERF_DURATION"])
max_error_rate = float(os.environ["PERF_MAX_ERROR_RATE"])
wall = int(os.environ["WALL_SECONDS"]) or 1

codes = collections.Counter(code for code, _ in rows)
# 201 Created is the only success for POST /v1/complaints.
ok = [t for code, t in rows if code == "201"]
n = len(rows)
errors = n - len(ok)
error_rate = 100.0 * errors / n


def pct(values, p):
    """Nearest-rank percentile. Small samples, so no interpolation."""
    if not values:
        return float("nan")
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p / 100.0 * len(s) + 0.5)) - 1))
    return s[k]


print(f"  requests dispatched   {n}")
print(f"  successful (201)      {len(ok)}")
print(f"  errors                {errors}  ({error_rate:.2f}%)")
print(f"  target rate           {target_rps} rps for {duration}s")
print(f"  wall clock            {wall}s  (achieved {n / wall:.1f} rps)")
print()
print("  status codes:")
for code, count in sorted(codes.items()):
    label = {"000": " (connection failed / timeout)"}.get(code, "")
    print(f"    {code}{label:32s} {count}")

if ok:
    print()
    print("  latency of successful requests (end-to-end, client-side):")
    for label, p in (("p50", 50), ("p95", 95), ("p99", 99)):
        print(f"    {label}  {pct(ok, p) * 1000:8.1f} ms")
    print(f"    min  {min(ok) * 1000:8.1f} ms")
    print(f"    max  {max(ok) * 1000:8.1f} ms")

if os.environ.get("PERF_JSON"):
    payload = {
        "target_rps": target_rps,
        "duration_seconds": duration,
        "wall_seconds": wall,
        "dispatched": n,
        "successful": len(ok),
        "errors": errors,
        "error_rate_percent": round(error_rate, 4),
        "status_codes": dict(codes),
        "latency_ms": {
            "p50": round(pct(ok, 50) * 1000, 2) if ok else None,
            "p95": round(pct(ok, 95) * 1000, 2) if ok else None,
            "p99": round(pct(ok, 99) * 1000, 2) if ok else None,
            "min": round(min(ok) * 1000, 2) if ok else None,
            "max": round(max(ok) * 1000, 2) if ok else None,
        },
        "caveat": (
            "Sandbox-scale indicative only — NOT a load test. Client, API, "
            "Postgres and Redis share one machine; sandbox data volumes; "
            "single API process. See docs/OPERATOR-CHECKLIST.md."
        ),
    }
    with open(os.environ["PERF_JSON"], "w") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    print(f"\n  wrote {os.environ['PERF_JSON']}")

print()
print("  " + "-" * 68)
print("  Sandbox-scale indicative only. This is NOT a load test, and these")
print("  numbers say nothing about production capacity. A real load test at")
print("  target volume is a go-live gate — see docs/OPERATOR-CHECKLIST.md.")
print("  " + "-" * 68)

if error_rate > max_error_rate:
    print(f"\nFAIL: error rate {error_rate:.2f}% exceeds PERF_MAX_ERROR_RATE={max_error_rate}%")
    sys.exit(1)
PY
