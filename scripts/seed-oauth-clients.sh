#!/usr/bin/env bash
# Seed the two demo oauth_clients rows with argon2id-hashed client
# secrets. The plain-text secrets are deliberately stable so SDK
# integrators can copy them from this file into a Postman collection
# or .env without needing to read a generated artifact.
#
# Plain-text demo credentials (sandbox-only — never used in production):
#   client_id=banco-demo-001   client_secret=banco-demo-001-secret   # pragma: allowlist secret
#   client_id=coopac-demo-002  client_secret=coopac-demo-002-secret  # pragma: allowlist secret
#
# Production onboarding (Part 8) issues hashes via the admin API and
# does not rely on this script.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$REPO_ROOT"

BANCO_HASH="$(uv run python -c 'import sys; sys.path.insert(0, "api"); from sbs_api.auth.oauth import hash_client_secret; print(hash_client_secret("banco-demo-001-secret"))')"
COOPAC_HASH="$(uv run python -c 'import sys; sys.path.insert(0, "api"); from sbs_api.auth.oauth import hash_client_secret; print(hash_client_secret("coopac-demo-002-secret"))')"

docker exec -e PGPASSWORD=sbs -i sbs-postgres \
  psql -U sbs -d sbs_dev -v ON_ERROR_STOP=1 <<SQL
INSERT INTO oauth_clients (
    client_id,
    institution_id,
    client_secret_hash,
    cert_thumbprint_required,
    created_at
) VALUES
    ('banco-demo-001',  'SBS-001234', '${BANCO_HASH}',  NULL, now()),
    ('coopac-demo-002', 'SBS-005678', '${COOPAC_HASH}', NULL, now())
ON CONFLICT (client_id) DO NOTHING;
SQL

echo "==> oauth_clients seeded"
echo "    banco-demo-001  -> SBS-001234"
echo "    coopac-demo-002 -> SBS-005678"
