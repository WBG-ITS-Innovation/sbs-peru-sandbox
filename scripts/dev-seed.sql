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
    created_at
) VALUES
    ('SBS-001234', 'BANCO_DEMO_001',  true, 60, 'v0.1.0', now()),
    ('SBS-005678', 'COOPAC_DEMO_002', true, 60, 'v0.1.0', now())
ON CONFLICT (institution_id) DO NOTHING;
