#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Tier 2 batch ingestion smoke test (Prompt 8).
#
# Stage flags (per spec §4):
#   stage-a          — POST /v1/batches happy path + 413 + checksum mismatch
#   stage-b          — arq worker processes a batch end-to-end (Workstream B)
#   stage-c          — GET /v1/batches/{batch_id}/rejections paginates correctly (Workstream C)
#   stage-d          — outbound webhook fires + retry + URL validation (Workstream D)
#   stage-e          — synthetic corpus generator produces FINANCIERA_DEMO_003 batch (Workstream E)
#   stage-g-contract — union of A–F's pytest assertions + Spectral + golden-sample byte-stability
#   stage-g-full     — stage-g-contract + the live-stack signed-callback test
#                       (compose worker + webhook-listener required up;
#                        scripts/smoke_stage_g_live.py drives the live path)
#   stage-h-contract — agent layer wired into canonical ingestion (in-process)
#   stage-h-full     — stage-h-contract + the live agent gate: signed POSTs on
#                       both tiers over mTLS, agent runs asserted in the live
#                       DB with a non-null model_provider
#                       (scripts/smoke_stage_h_live.py drives the live path)
#
# Pre-conditions:
#   stage-a … stage-f and stage-g-contract:
#     bash scripts/dev-up.sh   — Postgres + Redis + migrations + seed
#     Docker is running (the pytest fixture uses a pgvector testcontainer)
#   stage-g-full additionally requires:
#     docker compose up -d worker webhook-listener
#     The host API does NOT need to be running for stage-g-full; the
#     live path enqueues directly via arq, not via HTTP.
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
    ./node_modules/.bin/spectral lint api/openapi/sbs-api-v1.yaml --format=json --quiet 2>/dev/null \
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
    ./node_modules/.bin/spectral lint api/openapi/sbs-api-v1.yaml --format=json --quiet 2>/dev/null \
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
  stage-g-contract)
    step "Stage G (contract) — pytest union + Spectral + golden-sample"
    note "Contract-level acceptance: runs every workstream's pytest"
    note "assertions against the live testcontainer Postgres + httpx"
    note "MockTransport (signing + retry + URL validation contract)."
    note "Does NOT exercise the docker-compose worker container or the"
    note "webhook-listener container. stage-g-full covers those."
    uv run pytest -q --tb=short \
      tests/test_batch_endpoint.py \
      tests/test_complaints_source_backfill.py \
      tests/test_alembic_migration.py \
      tests/test_batch_worker.py \
      tests/test_batch_validation_uses_tier_1_models.py \
      tests/test_batch_status_endpoint.py \
      tests/test_batch_rejections_pagination.py \
      tests/test_webhook_signing.py \
      tests/test_webhook_url_validation.py \
      tests/test_webhook_delivery.py \
      tests/test_synthetic_corpus_generator.py \
      tests/test_fixture_conformance.py \
      tests/test_batch_storage_prune.py \
      tests/test_webhook_delivery_telemetry.py \
      || fail "stage-g-contract pytest assertions did not pass"

    note "Spectral lint 0 errors on api/openapi/sbs-api-v1.yaml"
    ./node_modules/.bin/spectral lint api/openapi/sbs-api-v1.yaml --format=json --quiet 2>/dev/null \
      | python -c "import json, sys; d=json.load(sys.stdin); errs=[r for r in d if r.get('severity')==0]; sys.exit(0 if not errs else 1)" \
      || fail "Spectral reports errors"

    note "Golden sample reproduces byte-stable from --seed 2026 --today 2026-05-20"
    uv run python scripts/generate-synthetic-corpus.py --golden > /tmp/sbs-prompt08-corpus-summary.json
    if ! git diff --quiet data/synthetic-corpus-golden/ 2>/dev/null; then
      fail "Golden sample regeneration produced a diff — commit the new bytes"
    fi

    echo
    echo "stage-g-contract: PASS"
    ;;
  stage-g-full)
    step "Stage G (full) — live-stack signed-callback test"
    note "Requires the docker-compose worker + webhook-listener services"
    note "to be running. Spec §7."
    note ""
    note "Sequence (scripts/smoke_stage_g_live.py):"
    note "  1. Confirm compose services up (postgres, redis, worker, webhook-listener)"
    note "  2. Poll webhook-state/ready (5s timeout)"
    note "  3. Insert batches row + write CSV to data/batches/"
    note "  4. Enqueue process_batch via live arq Redis"
    note "  5. Poll batch status until complete"
    note "  6. Tail webhook-listener log for PASS line"
    echo

    # Both halves always run. Aborting the live half on a contract
    # regression meant the only genuinely live assertion in this gate was
    # skipped exactly when the stack most needed checking, and the gate
    # reported failure without ever having exercised the live path.
    contract_rc=0
    bash "$0" stage-g-contract || contract_rc=$?
    if [[ $contract_rc -ne 0 ]]; then
      note "stage-g-contract FAILED (exit $contract_rc) — running the"
      note "live-stack check anyway so this gate still reports on it."
    fi

    echo
    step "Live-stack check"
    live_rc=0
    uv run python scripts/smoke_stage_g_live.py || live_rc=$?

    echo
    [[ $contract_rc -eq 0 ]] && echo "  contract half: PASS" || echo "  contract half: FAIL"
    [[ $live_rc -eq 0 ]] && echo "  live half:     PASS" || echo "  live half:     FAIL"
    if [[ $contract_rc -ne 0 || $live_rc -ne 0 ]]; then
      fail "stage-g-full: contract_rc=$contract_rc live_rc=$live_rc"
    fi
    echo "stage-g-full: PASS"
    ;;
  stage-h-contract)
    step "Stage H (contract) — agent layer wired into canonical ingestion"
    note "  tests/test_agent_ingest_wiring.py — both tiers dispatch the chain,"
    note "  DIValeVale runs ahead of Triage with one validation_audit row,"
    note "  dispatch cannot break the ingesting request, provider identity"
    note "  is persisted, and the record adapter invents no fields."
    note "  tests/test_orm_model_registry.py — every ORM model on disk is"
    note "  registered in Base.metadata."
    uv run pytest -q --tb=short \
      tests/test_agent_ingest_wiring.py \
      tests/test_orm_model_registry.py \
      || fail "stage-h-contract pytest assertions did not pass"
    echo
    echo "stage-h-contract: PASS"
    ;;
  stage-h-full)
    step "Stage H (full) — live agent gate across the docker network"
    note "Requires: docker compose postgres + redis + worker up with"
    note "SBS_API_AGENTS_PIPELINE_ENABLED=true, and the API running with"
    note "mTLS direct on :8443 with the pipeline enabled."
    note ""
    note "Sequence (scripts/smoke_stage_h_live.py):"
    note "  1. Confirm compose services + worker pipeline flag"
    note "  2. Confirm the API answers over mTLS"
    note "  3. Tier 1 signed POST /v1/complaints -> assert agent trace"
    note "  4. Tier 2 signed POST /v1/batches -> worker container -> assert"
    note "  5. Both tiers: validation_audit row + triage run with a"
    note "     non-null model_provider"
    echo

    contract_rc=0
    bash "$0" stage-h-contract || contract_rc=$?
    if [[ $contract_rc -ne 0 ]]; then
      note "stage-h-contract FAILED (exit $contract_rc) — running the live"
      note "gate anyway so this gate still reports on it."
    fi

    echo
    step "Live agent gate"
    live_rc=0
    uv run python scripts/smoke_stage_h_live.py || live_rc=$?

    echo
    [[ $contract_rc -eq 0 ]] && echo "  contract half: PASS" || echo "  contract half: FAIL"
    [[ $live_rc -eq 0 ]] && echo "  live half:     PASS" || echo "  live half:     FAIL"
    if [[ $contract_rc -ne 0 || $live_rc -ne 0 ]]; then
      fail "stage-h-full: contract_rc=$contract_rc live_rc=$live_rc"
    fi
    echo "stage-h-full: PASS"
    ;;
  *)
    fail "Unknown stage: $STAGE. Valid: stage-a stage-b stage-c stage-d stage-e stage-f stage-g-contract stage-g-full stage-h-contract stage-h-full"
    ;;
esac
