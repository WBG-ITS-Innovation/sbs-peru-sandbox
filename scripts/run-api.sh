#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run the FastAPI app locally for development.
#
# This script loads .env (if present) and runs the app via uvicorn with reload.
# Defaults are tuned for friction-free local dev:
#   - AUTH_STUB_ENABLED=true so tenant-binding endpoints accept the demo institution
#   - LOG_FORMAT=console for human-readable logs
#   - OTEL_TRACES_EXPORTER=console for visible spans
# Override per-call with: VAR=value bash scripts/run-api.sh
#
# Pre-requisites: postgres reachable at SBS_API_DATABASE_URL. Run
# `bash scripts/dev-up.sh` first if needed.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$REPO_ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

export SBS_API_AUTH_STUB_ENABLED="${SBS_API_AUTH_STUB_ENABLED:-true}"
export SBS_API_LOG_FORMAT="${SBS_API_LOG_FORMAT:-console}"
export SBS_API_OTEL_TRACES_EXPORTER="${SBS_API_OTEL_TRACES_EXPORTER:-console}"
export SBS_API_DATABASE_URL="${SBS_API_DATABASE_URL:-postgresql+asyncpg://sbs:sbs@localhost:5432/sbs_dev}" # pragma: allowlist secret
export SBS_API_RELOAD="${SBS_API_RELOAD:-true}"
export PYTHONPATH="$REPO_ROOT/api${PYTHONPATH:+:$PYTHONPATH}"

# mTLS — opt in by exporting SBS_API_MTLS_MODE=direct and having dev-ca/ present.
# When dev-ca/ is missing the runtime starts without TLS (auth-stub friendly).
if [[ -f dev-ca/ca.pem && -f dev-ca/sbs-suptech-sandbox.local.pem && "${SBS_API_MTLS_MODE:-disabled}" == "direct" ]]; then
  echo "==> mTLS direct mode: uvicorn will require client certs signed by dev-ca/ca.pem"
  export SBS_API_MTLS_MODE="direct"
  export SBS_API_UVICORN_SSL_CA_CERTS="${SBS_API_UVICORN_SSL_CA_CERTS:-$REPO_ROOT/dev-ca/ca.pem}"
  # Server cert: the dev CA issues a dedicated server cert with serverAuth EKU
  # and SAN covering sbs-suptech-sandbox.local, localhost, and 127.0.0.1.
  # Production overlay uses an SBS-PKI server cert.
  export SBS_API_UVICORN_SSL_CERTFILE="${SBS_API_UVICORN_SSL_CERTFILE:-$REPO_ROOT/dev-ca/sbs-suptech-sandbox.local.pem}"
  export SBS_API_UVICORN_SSL_KEYFILE="${SBS_API_UVICORN_SSL_KEYFILE:-$REPO_ROOT/dev-ca/sbs-suptech-sandbox.local-key.pem}"
else
  export SBS_API_MTLS_MODE="${SBS_API_MTLS_MODE:-disabled}"
fi

exec uv run python -m sbs_api
