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
  stage-c)
    step "Stage C — batch status + rejections pagination"
    note "  tests/test_batch_status_endpoint.py — 3 assertions"
    note "  tests/test_batch_rejections_pagination.py — 4 assertions"
    uv run pytest -q --tb=short \
      tests/test_batch_status_endpoint.py \
      tests/test_batch_rejections_pagination.py \
      || fail "stage-c assertions did not pass"
    note "Spectral lint 0 errors"
    ./node_modules/.bin/spectral lint api/openapi/sbs-api-v1.yaml --format=json 2>/dev/null \
      | python -c "import json, sys; d=json.load(sys.stdin); errs=[r for r in d if r.get('severity')==0]; sys.exit(0 if not errs else 1)" \
      || fail "Spectral reports errors"
    echo
    echo "stage-c: PASS"
    ;;
  stage-d)
    step "Stage D — webhook signing + delivery + URL validation"
    note "  tests/test_webhook_signing.py — 7 assertions (canonical shape,"
    note "  determinism, constant-time compare, header round-trip)"
    note "  tests/test_webhook_url_validation.py — 11 assertions (HTTPS,"
    note "  FQDN, public-IP, dev/test override, prod-boot-refusal)"
    note "  tests/test_webhook_delivery.py — 4 assertions (happy 200,"
    note "  retry on 500, dead-letter after 5 attempts, URL-rejected no-retry)"
    uv run pytest -q --tb=short \
      tests/test_webhook_signing.py \
      tests/test_webhook_url_validation.py \
      tests/test_webhook_delivery.py \
      || fail "stage-d assertions did not pass"
    echo
    echo "stage-d: PASS"
    ;;
  stage-e)
    step "Stage E — synthetic corpus + FINANCIERA_DEMO_003 + golden sample"
    note "  tests/test_synthetic_corpus_generator.py — 8 assertions"
    note "  (determinism, schema compliance, no unfilled placeholders,"
    note "  monetary range, golden-sample reproducibility,"
    note "  RUC checksum helper, pattern-cluster stub)"
    uv run pytest -q --tb=short \
      tests/test_synthetic_corpus_generator.py \
      || fail "stage-e assertions did not pass"
    note "Golden sample regenerates byte-stable from the deterministic seed"
    uv run python scripts/generate-synthetic-corpus.py --golden > /tmp/sbs-prompt08-corpus-summary.json
    if ! git diff --quiet data/synthetic-corpus-golden/ 2>/dev/null; then
      fail "Golden sample regeneration produced a diff — commit the new bytes"
    fi
    echo
    echo "stage-e: PASS"
    ;;
  stage-f)
    step "Stage F — hardening: fixture conformance + prune + telemetry"
    note "  tests/test_fixture_conformance.py — 16 assertions"
    note "  tests/test_batch_storage_prune.py — 4 assertions"
    note "  tests/test_webhook_delivery_telemetry.py — 5 assertions"
    uv run pytest -q --tb=short \
      tests/test_fixture_conformance.py \
      tests/test_batch_storage_prune.py \
      tests/test_webhook_delivery_telemetry.py \
      || fail "stage-f assertions did not pass"
    echo
    echo "stage-f: PASS"
    ;;
  stage-g-full)
    fail "Stage stage-g-full lands in Workstream G."
    ;;
  *)
    fail "Unknown stage: $STAGE. Valid: stage-a stage-b stage-c stage-d stage-e stage-g-full"
    ;;
esac
