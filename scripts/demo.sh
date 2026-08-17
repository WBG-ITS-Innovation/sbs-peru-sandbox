#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Deterministic demo replay for the May 25 sandbox kickoff.
#
# Generates synthetic Anexo 1-A complaints across the three demo
# institutions (BANCO_DEMO_001, COOPAC_DEMO_002, FINANCIERA_DEMO_003),
# packages each as a Tier 2 batch, enqueues processing on the live
# worker, polls until each batch reaches a terminal state, and tails
# the webhook-listener for the three PASS lines.
#
# Determinism: row CONTENT is byte-identical across runs at the same
# --seed. The one deliberate exception is complaint_id: this script
# passes a fresh --run-token to the generator on every run, which folds
# a per-run salt into the complaint_id tail (staying inside the route
# contract). Without it, re-running ingestion against a live database
# would collide on the complaint_id primary key and accept zero rows.
# The golden corpus and the determinism tests call the generator with
# no run token, so they stay byte-stable.
#
# Webhook signature timestamps are current-time-stamped per request
# (NOT deterministic; documented as expected — the canonical request
# includes the timestamp, so signatures differ per run).
#
# See ADR 0036 (synthetic corpus fidelity tiers) for the data shape
# and Prompt 8's session journal for the live-stack contract.
#
# Pre-requisites:
#   bash scripts/dev-up.sh
#   docker compose up -d worker webhook-listener
#
# Exit codes:
#   0  — all three batches reached `complete` and the listener logged
#        a PASS line for each within --max-wait
#   1  — generic failure
#   2  — required docker compose service not running
#   3  — synthetic corpus generation failed
#   4  — at least one batch failed or timed out
#   5  — dev CA leaf certs expire too soon (< 5 minutes)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$REPO_ROOT"

# --- Defaults ----------------------------------------------------------------

SCENARIO="tier2-batch"
SCALE="small"          # small (50 rows total) | full (200 rows total)
SEED="20260520"
WINDOW="30s"
DAYS="10"
MAX_WAIT="60"
PYTHONUNBUFFERED=1
export PYTHONUNBUFFERED

# Part 12 — agent pipeline. The demo path force-enables the pipeline so a
# previous shell-level export cannot silently route the demo away from the
# agent chain. The model provider defaults to `replay`, which reads
# pre-recorded fixtures from disk and logs a WARNING on every request
# saying so; every agent_run it produces carries model_provider='replay'.
# It used to default to `mock`, which is now test-only — canned tool calls
# reach agent_runs looking like analysis, and a demo audience cannot see
# the difference. An operator may pin a real backend by pre-exporting
# SBS_API_MODEL_PROVIDER, e.g.
# `SBS_API_MODEL_PROVIDER=on_prem bash scripts/demo.sh`.
export SBS_API_AGENTS_PIPELINE_ENABLED=true
export SBS_API_MODEL_PROVIDER="${SBS_API_MODEL_PROVIDER:-replay}"
echo "demo.sh: SBS_API_AGENTS_PIPELINE_ENABLED=${SBS_API_AGENTS_PIPELINE_ENABLED}" \
     "SBS_API_MODEL_PROVIDER=${SBS_API_MODEL_PROVIDER}"

# Demo institutions (mirror scripts/generate-synthetic-corpus.py:INSTITUTIONS).
INSTITUTIONS=("SBS-001234" "SBS-005678" "SBS-009012")

usage() {
  cat <<EOF
Usage: bash scripts/demo.sh [options]

Options:
  --scenario tier2-batch  (currently the only supported scenario)
  --scale {small|full}    small: 17 rows × 3 institutions = 51 rows / max-wait 60s
                          full:  67 rows × 3 institutions = 201 rows / max-wait 90s
                          full requires hour-5 status clean per Prompt 9 §3
  --seed N                deterministic seed (default 20260520)
  --window NN             wall-clock budget (default 30s)
  --days N                simulated absolute date range (default 10)
                          2026-05-15 to 2026-05-24
  --max-wait N            per-batch poll timeout in seconds
                          (default 60 for small, 90 for full)
  --help                  show this help
EOF
}

# --- Parse argv -------------------------------------------------------------

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scenario) SCENARIO="$2"; shift 2 ;;
    --scale)    SCALE="$2"; shift 2 ;;
    --seed)     SEED="$2"; shift 2 ;;
    --window)   WINDOW="$2"; shift 2 ;;
    --days)     DAYS="$2"; shift 2 ;;
    --max-wait) MAX_WAIT="$2"; shift 2 ;;
    --help|-h)  usage; exit 0 ;;
    *)          echo "unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

case "$SCALE" in
  small) ROWS_PER_INSTITUTION=17; [[ "$MAX_WAIT" == "60" ]] || true ;;
  full)
    ROWS_PER_INSTITUTION=67
    # If --max-wait was not explicitly bumped from default, bump it.
    if [[ "$MAX_WAIT" == "60" ]]; then
      MAX_WAIT=90
    fi
    ;;
  *) echo "invalid --scale: $SCALE (small|full)" >&2; exit 1 ;;
esac

# --- Pre-flight -------------------------------------------------------------

step() { echo; echo "==> $*"; }
note() { echo "  $*"; }
fail() { echo "FAIL: $*" >&2; exit "${2:-1}"; }

step "Pre-flight"

# 0. Python runner — prefer `uv run python` (matches the documented
#    workflow); fall back to the project's .venv when uv is not on
#    PATH (e.g. a stripped CI machine or a dev box that uses the
#    venv directly). Either path drives the same scripts against the
#    same interpreter.
if command -v uv >/dev/null 2>&1; then
  PY_RUN=(uv run python)
  note "Python runner: uv run python"
elif [[ -x .venv/bin/python ]]; then
  PY_RUN=(.venv/bin/python)
  note "Python runner: .venv/bin/python (uv not on PATH; falling back to venv)"
else
  fail "no Python runner available — install uv (https://astral.sh/uv) or create .venv" 1
fi

# 1. docker compose worker + webhook-listener up
note "docker compose status — worker + webhook-listener must be running"
SERVICES=$(docker compose ps --format '{{.Service}} {{.State}}' 2>/dev/null || true)
for required in worker webhook-listener; do
  if ! echo "$SERVICES" | grep -q "^$required running$"; then
    fail "$required not running. Bring up with: docker compose up -d worker webhook-listener" 2
  fi
done
note "compose services up"

# 2. dev CA leaf certs valid for at least 5 more minutes
if [[ -f dev-ca/sbs-001234-leaf.crt ]]; then
  if ! openssl x509 -in dev-ca/sbs-001234-leaf.crt -checkend 300 >/dev/null 2>&1; then
    fail "dev CA leaf cert expires within 5 minutes; regenerate via scripts/dev-ca.sh" 5
  fi
  note "dev CA certs valid for >= 5 minutes"
else
  note "dev CA cert not on disk (sandbox-only check skipped)"
fi

# 3. demo institutions seeded
note "demo institutions: ${INSTITUTIONS[*]}"

# --- Output directory --------------------------------------------------------

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTDIR="$REPO_ROOT/tmp/demo-run/$TIMESTAMP"
mkdir -p "$OUTDIR"
note "output → $OUTDIR"

# --- Generate synthetic corpus (deterministic) -------------------------------

step "Generating synthetic corpus (scale=$SCALE seed=$SEED rows/inst=$ROWS_PER_INSTITUTION)"

CORPUS_DIR="$OUTDIR/corpus"
mkdir -p "$CORPUS_DIR"

# Fresh per-run token so complaint_ids do not collide with rows already in
# the live database from a previous run. The generator folds it into the
# complaint_id tail (see scripts/generate-synthetic-corpus.py --run-token).
RUN_TOKEN="${TIMESTAMP}-${RANDOM}"
note "run token: $RUN_TOKEN"

if ! "${PY_RUN[@]}" scripts/generate-synthetic-corpus.py \
      --out "$CORPUS_DIR" \
      --rows-per-institution "$ROWS_PER_INSTITUTION" \
      --seed "$SEED" \
      --run-token "$RUN_TOKEN" >"$OUTDIR/generate.log" 2>&1; then
  fail "synthetic corpus generation failed; see $OUTDIR/generate.log" 3
fi

CORPUS_FILE_COUNT=$(find "$CORPUS_DIR" -type f -name "*.csv" | wc -l | tr -d ' ')
note "corpus files: $CORPUS_FILE_COUNT csv files"

if [[ "$CORPUS_FILE_COUNT" -lt 3 ]]; then
  fail "expected >= 3 corpus CSV files for the 3 demo institutions, got $CORPUS_FILE_COUNT" 3
fi

# --- Replay ------------------------------------------------------------------

step "Replaying batches (max_wait=${MAX_WAIT}s per batch)"

if ! "${PY_RUN[@]}" scripts/demo_replay.py \
      --corpus-dir "$CORPUS_DIR" \
      --out-dir "$OUTDIR" \
      --max-wait "$MAX_WAIT" \
      --institutions "${INSTITUTIONS[@]}"; then
  fail "demo replay failed; see $OUTDIR/summary.json for details" 4
fi

# --- Agent pipeline on the freshly-ingested complaints -----------------------
# The arq worker container ingests the batch but does not run the agent
# chain (its env keeps the pipeline off). Run it here, host-side, where
# SBS_API_MODEL_PROVIDER is set, so each new complaint gets agent_runs.

step "Running agent pipeline on new complaints"

if ! "${PY_RUN[@]}" scripts/run_agent_pipeline_on_new.py \
      >"$OUTDIR/agent-pipeline.log" 2>&1; then
  fail "agent pipeline on new complaints failed; see $OUTDIR/agent-pipeline.log" 4
fi
tail -n 3 "$OUTDIR/agent-pipeline.log" | sed 's/^/  /'

# --- Summary -----------------------------------------------------------------

step "Done"
note "summary: $OUTDIR/summary.json"
echo
if command -v jq >/dev/null 2>&1; then
  jq . "$OUTDIR/summary.json"
else
  cat "$OUTDIR/summary.json"
fi
echo
echo "demo.sh: PASS"
