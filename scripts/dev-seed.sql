-- Local-dev seed data.
--
-- Inserts the two demo institutions the smoke test, the developer-portal
-- examples, and ad-hoc curl exercises against the running API expect to
-- find. The smoke test posts complaints with institution_id SBS-001234;
-- the institutions.institution_id FK on complaints blocks the INSERT
-- without these rows.
--
-- Idempotent: ON CONFLICT DO NOTHING so dev-up.sh can re-run after a
-- pre-existing volume without erroring. The institution_id values match
-- the auth-stub default (SBS_API_AUTH_STUB_INSTITUTION_ID = SBS-001234)
-- and the cross-tenant test counterpart (SBS-005678).
--
-- Production never runs this script. Real institution onboarding lands
-- in Prompt 7+ alongside the institution-management API and the mTLS /
-- OAuth client-credential issuance flow.

INSERT INTO institutions (
    institution_id,
    display_name,
    onboarded,
    rate_limit_per_minute,
    schema_version,
    permitted_scopes,
    created_at
) VALUES
    ('SBS-001234', 'BANCO_DEMO_001',  true, 60, 'v0.1.0',
        ARRAY['complaints:write', 'complaints:read', 'batch:upload', 'status:read']::varchar[],
        now()),
    ('SBS-005678', 'COOPAC_DEMO_002', true, 60, 'v0.1.0',
        ARRAY['complaints:write', 'complaints:read', 'batch:upload', 'status:read']::varchar[],
        now())
ON CONFLICT (institution_id) DO NOTHING;

-- HMAC secrets for the two demo institutions. The active_secret values
-- are deliberately well-known constants for the sandbox; production
-- onboarding (Part 8) issues secrets via the admin API and never
-- commits them. Both secrets are 32 random bytes hex-encoded — usable
-- by any SDK author following the ADR 0027 amendment.
INSERT INTO institution_secrets (
    institution_id,
    active_secret,
    rotated_at,
    created_at
) VALUES
    ('SBS-001234',
        decode('4a5f1d2e8c7b9a3e5f2d1c8b9a3e5f2d4a5f1d2e8c7b9a3e5f2d1c8b9a3e5f2d', 'hex'),  -- pragma: allowlist secret
        now(), now()),
    ('SBS-005678',
        decode('1f2e3d4c5b6a79880f1e2d3c4b5a69877f8e9d0c1b2a39481f2e3d4c5b6a7988', 'hex'),  -- pragma: allowlist secret
        now(), now())
ON CONFLICT (institution_id) DO NOTHING;

-- OAuth client seeding cannot live in static SQL: argon2id hashes are
-- salted and non-deterministic, so the hash for a known plain-text
-- secret differs every time. Demo OAuth clients are produced by
-- `bash scripts/seed-oauth-clients.sh` (run after dev-up.sh) which
-- invokes the API's argon2 helper to compute fresh hashes and INSERT
-- them with ON CONFLICT DO NOTHING.
