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

-- Demo complaints for the supervisor UI narrative (Prompt 10).
--
-- scripts/seed_demo_narrative.py inserts agent_runs rows referencing
-- these three complaint_ids and was originally written assuming they
-- existed (either from the db_schema test fixture or from real Tier 1
-- ingestion). Neither path runs at dev-up time, so the narrative seed
-- failed against a fresh dev DB. These rows close that gap.
--
-- BCO-2026-000001 is the demo headline: the Conduct Analyst's narration edit adds
-- "comisión por mantenimiento" — the description_text below
-- deliberately omits that phrase from paragraph 2 so the scripted edit
-- has somewhere to land.
--
-- BCO-2026-000002 is the partial-failure target (BERT timeout + XGBoost
-- unavailable agent_run traces hang off it).
--
-- BCO-2026-000003 is the failed-run target (anonymizer error).
--
-- All three carry source='api_realtime' so they look like Tier 1
-- submissions in the cockpit, on SBS-001234 (BANCO_DEMO_001).
INSERT INTO complaints (
    complaint_id,
    institution_id,
    received_date,
    complainant_doc_type,
    product_category,
    channel,
    motivo_code,
    severity,
    description_text,
    description_language,
    complainant_age_range,
    complainant_district,
    submission_method,
    resolution_status,
    source
) VALUES
    (
        'BCO-2026-000001',
        'SBS-001234',
        '2026-05-20',
        'DNI',
        'TARJETA_CREDITO',
        'APP_MOVIL',
        'COBRO_INDEBIDO',
        'HIGH',
        E'Reclamo por cargos no informados en mi tarjeta de crédito.\n\nDurante los últimos tres meses he visto débitos recurrentes que no aparecen en el contrato original ni en la cartilla de información que firmé al momento de la apertura. Solicité explicación al canal de atención y no me dieron una respuesta clara sobre el origen del cargo.\n\nPido la devolución íntegra y la rectificación del cronograma.',
        'es',
        '35_44',
        '150100',
        'APP_MOVIL',
        'pendiente',
        'api_realtime'
    ),
    (
        'BCO-2026-000002',
        'SBS-001234',
        '2026-05-20',
        'DNI',
        'CUENTA_AHORRO',
        'AGENCIA',
        'COBRO_INDEBIDO',
        'HIGH',
        E'Cargos en mi cuenta de ahorros que no reconozco. La agencia indicó que se trata de una comisión por mantenimiento que nunca fue informada al momento de abrir la cuenta. Solicito devolución y aclaración.',
        'es',
        '45_54',
        '150100',
        'AGENCIA',
        'pendiente',
        'api_realtime'
    ),
    (
        'BCO-2026-000003',
        'SBS-001234',
        '2026-05-20',
        'DNI',
        'CREDITO_CONSUMO',
        'CALL_CENTER',
        'COBRO_INDEBIDO',
        'HIGH',
        E'Cobros indebidos en mi crédito de consumo. El monto de la cuota mensual aumentó sin previa notificación. Solicito explicación y devolución de las diferencias.',
        'es',
        '25_34',
        '150100',
        'CALL_CENTER',
        'pendiente',
        'api_realtime'
    )
ON CONFLICT (complaint_id) DO NOTHING;

-- Tier 2 batch complaints for COOPAC_DEMO_002 (Prompt 10 cockpit panel).
--
-- The supervisor cockpit renders Tier 1 (BANCO_DEMO_001 / SBS-001234)
-- and Tier 2 (COOPAC_DEMO_002 / SBS-005678) side by side. Without the
-- rows below the Tier 2 panel renders empty — a P10 demo-data
-- integrity bug, not a UI bug. The cockpit query is the source of
-- truth: ComplaintRecord WHERE institution_id = SBS-005678.
--
-- Each row carries source='batch' (ADR 0034) so the Tier 2 provenance
-- is recorded in the complaints column the cockpit and downstream
-- analytics will read once tier provenance becomes a filter. Today
-- the cockpit only filters by institution_id; the source value lets
-- a future "show only batch-ingested" toggle land without re-seeding.
--
-- received_date values fall inside the cockpit Tier 2 28-day window
-- relative to the May 25 demo anchor (2026-04-25..2026-05-23).
-- received_at is server_default=now() so a fresh seed lands inside
-- the 28-day window regardless of clock skew.
--
-- Narrative text is synthetic and PII-free (no DNI, card, phone,
-- email, or proper-name marker). COOPAC operations span agency,
-- cajero, and app-móvil channels to mirror a credit-union profile.
INSERT INTO complaints (
    complaint_id,
    institution_id,
    received_date,
    complainant_doc_type,
    product_category,
    channel,
    motivo_code,
    severity,
    description_text,
    description_language,
    complainant_age_range,
    complainant_district,
    submission_method,
    resolution_status,
    source
) VALUES
    (
        'COP-2026-000001',
        'SBS-005678',
        '2026-05-10',
        'DNI',
        'COOPAC',
        'AGENCIA',
        'DEMORA_ATENCION',
        'MEDIUM',
        E'Aporte mensual no acreditado en mi cuenta cooperativa después de cinco días hábiles. La agencia indica que la conciliación está pendiente. Solicito la acreditación correspondiente.',
        'es',
        '35_44',
        '150100',
        'AGENCIA',
        'pendiente',
        'batch'
    ),
    (
        'COP-2026-000002',
        'SBS-005678',
        '2026-05-12',
        'DNI',
        'CREDITOS',
        'APP_MOVIL',
        'INFORMACION_INCORRECTA',
        'MEDIUM',
        E'El simulador de la app mostró una cuota distinta a la del contrato firmado. La diferencia se mantiene en tres cuotas consecutivas. Pido revisión del cronograma.',
        'es',
        '25_34',
        '150100',
        'APP_MOVIL',
        'pendiente',
        'batch'
    ),
    (
        'COP-2026-000003',
        'SBS-005678',
        '2026-05-15',
        'DNI',
        'DEPOSITOS',
        'AGENCIA',
        'COBRO_INDEBIDO',
        'HIGH',
        E'Cargo de mantenimiento de cuenta aplicado pese a saldo promedio superior al mínimo informado al momento de la apertura. Solicito la devolución y la corrección del estado de cuenta.',
        'es',
        '45_54',
        '150100',
        'AGENCIA',
        'pendiente',
        'batch'
    ),
    (
        'COP-2026-000004',
        'SBS-005678',
        '2026-05-18',
        'DNI',
        'TARJETA_DEBITO',
        'WEB',
        'OPERACION_NO_RECONOCIDA',
        'HIGH',
        E'Operación en cajero externo que no reconozco, por monto inferior al límite diario. Bloqueé la tarjeta el mismo día. Solicito la reversión y la investigación del punto de débito.',
        'es',
        '35_44',
        '150100',
        'CAJERO',
        'pendiente',
        'batch'
    ),
    (
        'COP-2026-000005',
        'SBS-005678',
        '2026-05-20',
        'DNI',
        'CREDITOS',
        'TELEFONO',
        'CALIDAD_SERVICIO',
        'LOW',
        E'Llamada al call center con espera superior a treinta minutos para una consulta de saldo. Solicito que se revise el dimensionamiento del canal en horario de mediodía.',
        'es',
        '55_64',
        '150100',
        'OTRO',
        'pendiente',
        'batch'
    )
ON CONFLICT (complaint_id) DO NOTHING;
