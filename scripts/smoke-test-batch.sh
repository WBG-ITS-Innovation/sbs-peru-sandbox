#!/usr/bin/env bash
# Tier 2 batch ingestion smoke test (Prompt 8).
#
# Stage flags (per spec §4):
#   stage-a       — POST /v1/batches happy path + 413 + checksum mismatch
#   stage-b       — arq worker processes a batch end-to-end (Workstream B)
#   stage-c       — GET /v1/batches/{batch_id}/rejections paginates correctly (Workstream C)
#   stage-d       — outbound webhook fires + retry + URL validation (Workstream D)
#   stage-e       — synthetic corpus generator produces FINANCIERA_DEMO_003 batch (Workstream E)
#   stage-g-full  — full end-to-end against the running mTLS API (Workstream G)
#
# Workstream A only requires stage-a to pass. The stages after a land
# with their respective workstreams.
#
# Pre-conditions:
#   1. bash scripts/dev-up.sh   — Postgres + Redis + migrations + seed
#   2. Docker is running (the test fixture uses a pgvector testcontainer)
#
# Exit codes:
#   0 — stage passed
#   non-zero — first failed assertion

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$REPO_ROOT"

STAGE="${1:-stage-a}"

fail() { echo "FAIL: $*" >&2; exit 1; }
note() { echo "  $*"; }
step() { echo; echo "==> $*"; }

case "$STAGE" in
  stage-a)
    step "Stage A — Tier 2 batch endpoint (multipart upload, 413, checksum mismatch)"
    note "Running pytest assertions against the live stack:"
    note "  tests/test_batch_endpoint.py — 7 assertions (happy 202+Location, status row,"
    note "  checksum mismatch 400, manifest 400, malformed manifest 400, cross-tenant 404, oversize 413)"
    note "  tests/test_complaints_source_backfill.py — 2 assertions (defaults + Tier 1 writes api_realtime)"
    note "  tests/test_alembic_migration.py — clean migration to revision 20260520_0001"
    uv run pytest -q --tb=short \
      tests/test_batch_endpoint.py \
      tests/test_complaints_source_backfill.py \
      tests/test_alembic_migration.py \
      || fail "stage-a pytest assertions did not pass"
    note "Spectral lint check on api/openapi/sbs-api-v1.yaml"
    ./node_modules/.bin/spectral lint api/openapi/sbs-api-v1.yaml --format=json 2>/dev/null \
      | python -c "import json, sys; d=json.load(sys.stdin); errs=[r for r in d if r.get('severity')==0]; sys.exit(0 if not errs else 1)" \
      || fail "Spectral reports errors"
    echo
    echo "stage-a: PASS"
    ;;
  stage-b)
    step "Stage B — arq worker processes a batch end-to-end"
    note "Worker function called in-process against live Postgres:"
    note "  tests/test_batch_worker.py — 4 assertions (happy path, mixed rows,"
    note "  idempotent on terminal, missing-file → failed)"
    note "  tests/test_batch_validation_uses_tier_1_models.py — 2 assertions"
    note "  (Complaint class identity; ComplaintSubmission annotation)"
    uv run pytest -q --tb=short \
      tests/test_batch_worker.py \
      tests/test_batch_validation_uses_tier_1_models.py \
      || fail "stage-b pytest assertions did not pass"
    echo
    echo "stage-b: PASS"
    ;;
  stage-c|stage-d|stage-e|stage-g-full)
    fail "Stage $STAGE lands in the workstream that owns it (C/D/E/G respectively)."
    ;;
  *)
    fail "Unknown stage: $STAGE. Valid: stage-a stage-b stage-c stage-d stage-e stage-g-full"
    ;;
esac
