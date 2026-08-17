#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Re-export the sbs-demo realm from a running Keycloak container.
#
# Used when a developer has tweaked the realm via the admin UI
# (http://localhost:8081, admin / admin) and wants to capture the change
# into the committed JSON. The realm JSON in this directory is the
# source of truth; running-container state is not.
#
# Usage:
#   bash infra/keycloak/export-realm.sh
#
# Pre-requisites:
#   docker compose is running, Keycloak is healthy
#   jq is installed locally (for pretty-printing)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="${REPO_ROOT}/infra/keycloak/realm-sbs-demo.json"

if ! command -v jq >/dev/null 2>&1; then
    echo "ERROR: jq is required (brew install jq | apt install jq)" >&2
    exit 1
fi

if ! docker compose -f "${REPO_ROOT}/docker-compose.yaml" ps keycloak --status running --quiet >/dev/null 2>&1; then
    echo "ERROR: keycloak service is not running. Start it with:" >&2
    echo "  docker compose up -d keycloak" >&2
    exit 1
fi

echo "==> exporting realm sbs-demo from running container"

# kc.sh export runs the realm export inside the container. We point it
# at /tmp so we don't accidentally overwrite the imported file on the
# bind mount.
docker compose -f "${REPO_ROOT}/docker-compose.yaml" exec -T keycloak \
    /opt/keycloak/bin/kc.sh export \
    --dir /tmp/kc-export \
    --realm sbs-demo \
    --users realm_file

echo "==> copying export out of container"

TMP_EXPORT="$(mktemp -d)"
docker compose -f "${REPO_ROOT}/docker-compose.yaml" cp \
    keycloak:/tmp/kc-export/sbs-demo-realm.json \
    "${TMP_EXPORT}/sbs-demo-realm.json"

echo "==> pretty-printing and stripping volatile fields"

# Sort keys for deterministic diffs; drop a few fields that change on
# every export but carry no decision content.
jq --sort-keys '
    del(
        .createdTimestamp,
        .users[]?.createdTimestamp,
        .clients[]?.id,
        .users[]?.id,
        .roles.realm[]?.id,
        .roles.client[]?[]?.id
    )
' "${TMP_EXPORT}/sbs-demo-realm.json" > "${OUT}"

rm -rf "${TMP_EXPORT}"

echo "==> wrote ${OUT}"
echo ""
echo "Review the diff before committing:"
echo "  git diff infra/keycloak/realm-sbs-demo.json"
