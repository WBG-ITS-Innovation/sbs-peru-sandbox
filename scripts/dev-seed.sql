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
    tier_classification,
    rate_limit_per_minute,
    schema_version,
    permitted_scopes,
    created_at
) VALUES
    ('SBS-001234', 'BANCO_DEMO_001',      true, 'large', NULL, 'v0.1.0',
        ARRAY['complaints:write', 'complaints:read', 'batch:upload', 'status:read']::varchar[],
        now()),
    ('SBS-005678', 'COOPAC_DEMO_002',     true, 'small', NULL, 'v0.1.0',
        ARRAY['complaints:write', 'complaints:read', 'batch:upload', 'status:read']::varchar[],
        now()),
    ('SBS-009012', 'FINANCIERA_DEMO_003', true, 'small', NULL, 'v0.1.0',
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
        now(), now()),
    ('SBS-009012',
        decode('2b3c4d5e6f70819203041526374859602b3c4d5e6f70819203041526374859ab', 'hex'),  -- pragma: allowlist secret
        now(), now())
ON CONFLICT (institution_id) DO NOTHING;

-- OAuth client seeding cannot live in static SQL: argon2id hashes are
-- salted and non-deterministic, so the hash for a known plain-text
-- secret differs every time. Demo OAuth clients are produced by
-- `bash scripts/seed-oauth-clients.sh` (run after dev-up.sh) which
-- invokes the API's argon2 helper to compute fresh hashes and INSERT
-- them with ON CONFLICT DO NOTHING.

-- Outbound webhook secrets for the two demo institutions (Prompt 8 /
-- ADR 0035). Mirrors institution_secrets shape; the kid column carries
-- `sandbox-v1` so the X-SBS-Key-Id header on outbound callbacks is
-- predictable for SDK writers.
INSERT INTO outbound_webhook_secrets (
    institution_id,
    kid,
    active_secret,
    rotated_at,
    created_at
) VALUES
    ('SBS-001234', 'sandbox-v1',
        decode('a1b2c3d4e5f607182930415263748596a1b2c3d4e5f607182930415263748596', 'hex'),  -- pragma: allowlist secret
        now(), now()),
    ('SBS-005678', 'sandbox-v1',
        decode('5f4e3d2c1b0a99887766554433221100ffeeddccbbaa99887766554433221100', 'hex'),  -- pragma: allowlist secret
        now(), now()),
    ('SBS-009012', 'sandbox-v1',
        decode('c0d1e2f30415263748596a7b8c9d0e1fc0d1e2f30415263748596a7b8c9d0e1f', 'hex'),  -- pragma: allowlist secret
        now(), now())
ON CONFLICT (institution_id) DO NOTHING;

-- Webhook callback URLs pointing at the docker-compose `webhook-listener`
-- service. These URLs fail all three validation checks (HTTP not HTTPS,
-- bare hostname, private IP after Docker DNS resolution). The
-- SBS_API_ALLOW_INSECURE_WEBHOOK_URLS=true env override (gated to
-- environment=dev|test) bypasses the checks for the sandbox.
INSERT INTO institution_webhook_configs (
    institution_id,
    callback_url,
    enabled,
    created_at
) VALUES
    ('SBS-001234', 'http://webhook-listener:8080/sbs-callback', true, now()),
    ('SBS-005678', 'http://webhook-listener:8080/sbs-callback', true, now()),
    ('SBS-009012', 'http://webhook-listener:8080/sbs-callback', true, now())
ON CONFLICT (institution_id) DO NOTHING;
