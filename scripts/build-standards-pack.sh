#!/usr/bin/env bash
# Build the SBS standards pack v0.1 tarball.
#
# Populates standards-pack/ from authoritative sources elsewhere in
# the repository (api/openapi/, sdk-helpers/, error catalog), computes
# checksums.sha256, writes manifest.json with build-time provenance,
# and produces dist/standards-pack-v0.1.0.tar.gz + a .sha256 companion.
#
# See ADR 0039 (distribution + manifest shape) and ADR 0038 (helper
# scope). Convenience: `make standards-pack`.
#
# Exit codes:
#   0  pack built, tarball produced, manifest schema-validates
#   1  generic failure
#   2  required source missing (openapi spec, helper, error catalog)
#   3  manifest schema validation failed
#   4  checksum verification failed on the produced tarball
#   5  git not available (needed for the commit SHA in manifest)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$REPO_ROOT"

PACK_NAME="sbs-complaints-standards-pack"
PACK_VERSION="0.1.0"
MANIFEST_SCHEMA_VERSION="0.1.0"
WEBHOOK_SIGNATURE_VERSION="v1"
API_MIN_VERSION="0.1.0"
API_EXCLUSIVE_MAX_VERSION="1.0.0"
PUBLISHER="SBS Peru via WBG ITS Innovation Office"
LICENSE="LicenseRef-sandbox-pending-legal-review"
PORTAL_URL="https://api-sandbox.sbs.gob.pe/v1/portal/"

STANDARDS_PACK_DIR="$REPO_ROOT/standards-pack"
DIST_DIR="$REPO_ROOT/dist"
TARBALL="$DIST_DIR/standards-pack-v${PACK_VERSION}.tar.gz"
TARBALL_SHA256="$TARBALL.sha256"

log() { printf "==> %s\n" "$*"; }
fail() { printf "ERROR: %s\n" "$*" >&2; exit "${2:-1}"; }

# --- Pre-flight ---------------------------------------------------------------

command -v git >/dev/null 2>&1 || fail "git not available" 5
[[ -f api/openapi/sbs-api-v1.yaml ]] || fail "missing api/openapi/sbs-api-v1.yaml" 2
[[ -f api/openapi/error-catalog.md ]] || fail "missing api/openapi/error-catalog.md" 2
[[ -d api/openapi/schemas ]] || fail "missing api/openapi/schemas/" 2
[[ -d sdk-helpers/python ]] || fail "missing sdk-helpers/python/" 2
[[ -d sdk-helpers/typescript ]] || fail "missing sdk-helpers/typescript/" 2

GIT_COMMIT="$(git rev-parse HEAD)"
GENERATED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

log "building pack name=$PACK_NAME version=$PACK_VERSION"
log "git_commit=$GIT_COMMIT generated_at=$GENERATED_AT"

# --- Clean and re-populate the pack tree --------------------------------------
# Preserve manifest.schema.json and README.md (hand-maintained).

log "cleaning generated content under $STANDARDS_PACK_DIR"
rm -rf \
  "$STANDARDS_PACK_DIR/openapi" \
  "$STANDARDS_PACK_DIR/schemas" \
  "$STANDARDS_PACK_DIR/catalogs" \
  "$STANDARDS_PACK_DIR/sdk-helpers" \
  "$STANDARDS_PACK_DIR/examples" \
  "$STANDARDS_PACK_DIR/recipes" \
  "$STANDARDS_PACK_DIR/manifest.json" \
  "$STANDARDS_PACK_DIR/checksums.sha256"

mkdir -p \
  "$STANDARDS_PACK_DIR/openapi" \
  "$STANDARDS_PACK_DIR/schemas" \
  "$STANDARDS_PACK_DIR/catalogs" \
  "$STANDARDS_PACK_DIR/sdk-helpers/python" \
  "$STANDARDS_PACK_DIR/sdk-helpers/typescript" \
  "$STANDARDS_PACK_DIR/examples" \
  "$STANDARDS_PACK_DIR/recipes"

# --- OpenAPI spec ------------------------------------------------------------

log "copying OpenAPI spec"
# The OpenAPI filename carries the spec's major.minor (v0.1) — distinct
# from the pack's semver (PACK_VERSION). The spec version moves with the
# wire contract; the pack version moves with the publication.
cp api/openapi/sbs-api-v1.yaml \
   "$STANDARDS_PACK_DIR/openapi/sbs-complaints-v0.1.yaml"

# --- JSON Schemas -----------------------------------------------------------

log "copying JSON Schemas"
cp api/openapi/schemas/*.json "$STANDARDS_PACK_DIR/schemas/"

# --- Error catalog -----------------------------------------------------------

log "copying error catalog (markdown)"
cp api/openapi/error-catalog.md "$STANDARDS_PACK_DIR/catalogs/"

# --- SDK helpers -------------------------------------------------------------

log "copying SDK helpers"
cp sdk-helpers/python/sbs_webhooks.py \
   sdk-helpers/python/pyproject.toml \
   sdk-helpers/python/README.md \
   "$STANDARDS_PACK_DIR/sdk-helpers/python/"
# Copy the helper test as a vendored CI-passes-in-repo proof.
mkdir -p "$STANDARDS_PACK_DIR/sdk-helpers/python/tests"
cp sdk-helpers/python/tests/test_sbs_webhooks.py \
   "$STANDARDS_PACK_DIR/sdk-helpers/python/tests/"

cp sdk-helpers/typescript/src/index.ts \
   "$STANDARDS_PACK_DIR/sdk-helpers/typescript/index.ts"
cp sdk-helpers/typescript/package.json \
   sdk-helpers/typescript/README.md \
   sdk-helpers/typescript/jest.config.js \
   sdk-helpers/typescript/tsconfig.cjs.json \
   sdk-helpers/typescript/tsconfig.esm.json \
   sdk-helpers/typescript/tsconfig.types.json \
   "$STANDARDS_PACK_DIR/sdk-helpers/typescript/"

# --- Example payloads (extracted from the OpenAPI spec's examples block) ----

log "generating example payloads"
uv run python scripts/build-standards-pack-examples.py \
  --spec api/openapi/sbs-api-v1.yaml \
  --out "$STANDARDS_PACK_DIR/examples"

# --- Recipes ----------------------------------------------------------------
# Recipes live in standards-pack/recipes/ as authored content. The build
# does not regenerate them — they are source files. They land via
# workstream E.1 and E.2.

if [[ -d "$REPO_ROOT/standards-pack-recipes-source" ]]; then
  log "copying recipes from standards-pack-recipes-source/"
  cp "$REPO_ROOT"/standards-pack-recipes-source/*.md \
     "$STANDARDS_PACK_DIR/recipes/"
fi
# Otherwise the recipes are committed directly under standards-pack/recipes/
# (workstream E lands them there). The build doesn't re-write the directory.

if ! ls "$STANDARDS_PACK_DIR/recipes"/*.md >/dev/null 2>&1; then
  log "WARNING: no recipes/*.md found — pack will be incomplete until E.1/E.2 lands"
fi

# --- Manifest ----------------------------------------------------------------

log "writing manifest.json"
cat > "$STANDARDS_PACK_DIR/manifest.json" <<EOF
{
  "manifest_schema_version": "$MANIFEST_SCHEMA_VERSION",
  "name": "$PACK_NAME",
  "version": "$PACK_VERSION",
  "status": "sandbox",
  "publisher": "$PUBLISHER",
  "license": "$LICENSE",
  "git_commit": "$GIT_COMMIT",
  "generated_at": "$GENERATED_AT",
  "portal_url": "$PORTAL_URL",
  "webhook_signature_version": "$WEBHOOK_SIGNATURE_VERSION",
  "api_server_compatibility": {
    "min_version": "$API_MIN_VERSION",
    "exclusive_max_version": "$API_EXCLUSIVE_MAX_VERSION"
  },
  "contains": ["openapi", "schemas", "catalogs", "sdk-helpers", "examples", "recipes"]
}
EOF

# --- Validate manifest against its schema -----------------------------------

log "validating manifest against schema"
uv run python -c "
import json, pathlib, sys
import jsonschema
schema = json.loads(pathlib.Path('$STANDARDS_PACK_DIR/manifest.schema.json').read_text())
manifest = json.loads(pathlib.Path('$STANDARDS_PACK_DIR/manifest.json').read_text())
try:
    jsonschema.validate(manifest, schema)
    print('manifest schema-validates')
except jsonschema.exceptions.ValidationError as exc:
    print(f'MANIFEST INVALID: {exc.message}', file=sys.stderr)
    sys.exit(3)
"

# --- Compute checksums.sha256 -----------------------------------------------
# Every file inside standards-pack/ (excluding checksums.sha256 itself).

log "computing per-file SHA-256 → checksums.sha256"
(
  cd "$STANDARDS_PACK_DIR"
  find . -type f \
    -not -name "checksums.sha256" \
    -not -path "./__pycache__/*" \
    | sort | sed 's|^\./||' \
    | xargs shasum -a 256 > checksums.sha256
)

# --- Produce the tarball ----------------------------------------------------

log "tarballing → $TARBALL"
mkdir -p "$DIST_DIR"
( cd "$REPO_ROOT" && tar -czf "$TARBALL" --no-mac-metadata --no-xattrs standards-pack/ 2>/dev/null \
  || tar -czf "$TARBALL" standards-pack/ )
shasum -a 256 "$TARBALL" | awk '{print $1"  "(NF==2 ? $2 : $NF)}' > "$TARBALL_SHA256"

# --- Verify the tarball checksums --------------------------------------------

log "verifying tarball SHA-256"
(
  cd "$DIST_DIR"
  shasum -a 256 -c "$(basename "$TARBALL_SHA256")" || exit 4
)

# --- Final report -----------------------------------------------------------

log "tarball: $TARBALL"
log "tarball sha256: $(awk '{print $1}' "$TARBALL_SHA256")"
log "tarball size: $(wc -c < "$TARBALL") bytes"
log "git_commit: $GIT_COMMIT"
log "manifest version: $PACK_VERSION"
log "DONE"
