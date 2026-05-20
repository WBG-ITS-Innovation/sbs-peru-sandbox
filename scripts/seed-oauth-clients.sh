#!/usr/bin/env bash
# Seed the three demo oauth_clients rows with argon2id-hashed client
# secrets. The plain-text secrets are deliberately stable so SDK
# integrators can copy them from this file into a Postman collection
# or .env without needing to read a generated artifact.
#
# Plain-text demo credentials (sandbox-only — never used in production):
#   client_id=banco-demo-001       client_secret=banco-demo-001-secret       # pragma: allowlist secret
#   client_id=coopac-demo-002      client_secret=coopac-demo-002-secret      # pragma: allowlist secret
#   client_id=financiera-demo-003  client_secret=financiera-demo-003-secret  # pragma: allowlist secret
#
# Production onboarding (Part 8) issues hashes via the admin API and
# does not rely on this script.
#
# After seeding the rows, this script also populates the
# ``cert_thumbprint_required`` column from ``institution_certificates``
# (closes the Prompt 7 Day-2 deferral). The lookup is per-institution
# and uses the institution's most recent non-revoked cert.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
cd "$REPO_ROOT"

BANCO_HASH="$(uv run python -c 'import sys; sys.path.insert(0, "api"); from sbs_api.auth.oauth import hash_client_secret; print(hash_client_secret("banco-demo-001-secret"))')"
COOPAC_HASH="$(uv run python -c 'import sys; sys.path.insert(0, "api"); from sbs_api.auth.oauth import hash_client_secret; print(hash_client_secret("coopac-demo-002-secret"))')"
FINANCIERA_HASH="$(uv run python -c 'import sys; sys.path.insert(0, "api"); from sbs_api.auth.oauth import hash_client_secret; print(hash_client_secret("financiera-demo-003-secret"))')"

docker exec -e PGPASSWORD=sbs -i sbs-postgres \
  psql -U sbs -d sbs_dev -v ON_ERROR_STOP=1 <<SQL
INSERT INTO oauth_clients (
    client_id,
    institution_id,
    client_secret_hash,
    cert_thumbprint_required,
    created_at
) VALUES
    ('banco-demo-001',      'SBS-001234', '${BANCO_HASH}',      NULL, now()),
    ('coopac-demo-002',     'SBS-005678', '${COOPAC_HASH}',     NULL, now()),
    ('financiera-demo-003', 'SBS-009012', '${FINANCIERA_HASH}', NULL, now())
ON CONFLICT (client_id) DO NOTHING;

-- ADR 0032 + Prompt 7 Day-2 deferral: populate cert_thumbprint_required
-- from the institution's current cert. Bind each oauth_client row to the
-- most recent non-revoked certificate for that institution. Idempotent —
-- safe to re-run on every dev-up.sh.
UPDATE oauth_clients oc
SET cert_thumbprint_required = ic.sha256_thumbprint
FROM (
    SELECT DISTINCT ON (institution_id)
        institution_id, sha256_thumbprint
    FROM institution_certificates
    WHERE revoked_at IS NULL
    ORDER BY institution_id, created_at DESC
) ic
WHERE oc.institution_id = ic.institution_id;
SQL

echo "==> oauth_clients seeded"
echo "    banco-demo-001       -> SBS-001234"
echo "    coopac-demo-002      -> SBS-005678"
echo "    financiera-demo-003  -> SBS-009012"
echo "==> cert_thumbprint_required populated from institution_certificates"
