#!/usr/bin/env bash
# Build the SBS standards pack v0.1 tarball.
#
# Populates standards-pack/ from authoritative sources elsewhere in
# the repository (api/openapi/, sdk-helpers/, error catalog), computes
# checksums.sha256, writes manifest.json with build-time provenance,
# and produces dist/standards-pack-v${PACK_VERSION}.tar.gz + a .sha256 companion.
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
# Preserved (hand-authored): manifest.schema.json, README.md, recipes/.
# Wiped (regenerated):       openapi/, schemas/, catalogs/, sdk-helpers/,
#                            examples/, manifest.json, checksums.sha256.

log "cleaning generated content under $STANDARDS_PACK_DIR"
rm -rf \
  "$STANDARDS_PACK_DIR/openapi" \
  "$STANDARDS_PACK_DIR/schemas" \
  "$STANDARDS_PACK_DIR/catalogs" \
  "$STANDARDS_PACK_DIR/sdk-helpers" \
  "$STANDARDS_PACK_DIR/examples" \
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
# Recipes are hand-authored content committed directly under
# standards-pack/recipes/. The build neither generates them nor
# wipes them — only verifies they are present so the pack ships with
# the documented Java/Go/Python/TypeScript verification surface.

if ! ls "$STANDARDS_PACK_DIR/recipes"/*.md >/dev/null 2>&1; then
  log "WARNING: no recipes/*.md found under standards-pack/recipes/"
  log "         (E.1 Java+Go webhook snippets + Python/TypeScript pointers"
  log "          land there)"
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
  "contains": ["openapi", "schemas", "catalogs", "sdk-helpers", "examples", "recipes"],
  "attestation": {
    "type": "none",
    "rationale": "v0.1 sandbox release. SLSA + cosign attestation land at v0.2 with OCI artifact distribution per ADR 0039."
  }
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

# --- Produce the tarball (reproducible-build flags) -------------------------
# Per ADR 0039 §Consequences (integrity gap) and second-opinion review:
# gzip embeds an mtime by default, which makes two clean builds at the
# same commit produce different bytes even though every file inside is
# identical. SOURCE_DATE_EPOCH + `gzip -n` + tar's --sort=name +
# --mtime + --owner=0 + --group=0 + --numeric-owner make the tarball
# byte-reproducible across builds at the same git commit.

SOURCE_DATE_EPOCH="$(git log -1 --format=%ct HEAD)"
export SOURCE_DATE_EPOCH

log "tarballing (reproducible: SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH) → $TARBALL"
mkdir -p "$DIST_DIR"

# Use GNU-style flags where available; macOS bsdtar accepts most of these
# but not all. Detect at runtime.
if tar --version 2>&1 | grep -q "GNU tar"; then
  ( cd "$REPO_ROOT" \
    && tar --sort=name \
           --mtime="@$SOURCE_DATE_EPOCH" \
           --owner=0 --group=0 --numeric-owner \
           -cf - standards-pack/ \
       | gzip -n > "$TARBALL" )
else
  # bsdtar on macOS — emit a deterministic-ish tarball; full
  # cross-platform byte-reproducibility requires GNU tar in CI.
  ( cd "$REPO_ROOT" \
    && tar --no-mac-metadata --no-xattrs \
           -cf - standards-pack/ 2>/dev/null \
       | gzip -n > "$TARBALL" )
fi
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
