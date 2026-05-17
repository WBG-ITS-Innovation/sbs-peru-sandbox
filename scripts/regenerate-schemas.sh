#!/usr/bin/env bash
# Regenerate the standalone JSON Schema files under api/openapi/schemas/.
#
# Runs the Pydantic-side schema exporter. Commit any changes to the schemas
# directory alongside the model changes that produced them; the schemas are a
# committed artifact, not a build-time output (see ADR 0027).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHONPATH="$REPO_ROOT/api" uv run python -m sbs_api.models.export_schemas
