#!/usr/bin/env bash
# Serve the SBS developer portal on http://localhost:8080.
#
# The portal is a single HTML page that loads Stoplight Elements from a CDN
# and points it at api/openapi/sbs-api-v1.yaml. The OpenAPI document is
# served from the same origin so Elements can fetch it without CORS.
#
# Stop the server with Ctrl-C.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8080}"

echo "Serving SBS developer portal on http://localhost:${PORT}/"
echo "OpenAPI document: api/openapi/sbs-api-v1.yaml"
echo "Press Ctrl-C to stop."

cd "$REPO_ROOT/api"
exec python -m http.server "$PORT"
