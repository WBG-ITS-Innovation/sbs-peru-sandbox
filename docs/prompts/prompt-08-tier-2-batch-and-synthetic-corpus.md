# Prompt 8 — Tier 2 Batch Ingestion + Synthetic Data Corpus + Webhook Outbound Signing

- **Date target:** 2026-05-20
- **Prompt:** 8
- **Part:** 4 (closing — first time)
- **Slug:** tier-2-batch-and-synthetic-corpus
- **Branch:** `part-04/tier-2-batch-and-synthetic-corpus`
- **Predecessor:** Prompt 7 (PR #35 merged to `main` at `6061dbe`; 320 tests pass; `scripts/smoke-test-auth.sh` green end-to-end; auth chain real not stubbed; mTLS + HMAC + OAuth + rate-limiter all live).
- **Expected duration:** Truncated path (A0 → A → B → C → D → G → H, with E and F dropped at the hour-9 boundary) is 11-13 hours. Full path (everything lands cleanly) is 14-17 hours. The hour-9 time-box is structural specifically because the full path *will* run past 9 hours and the question is which items drop. Working assumption: full path runs unless something concrete forces the drop. **Hour-9 rule see §3.**
- **Harness:** Full. No lighter-harness shortcuts. Pre-draft GPT pressure-test in a fresh Claude.ai chat is mandatory. Cross-review at closeout uses gpt-5.4 via Azure OpenAI WBG ITS tenancy (same backend as Prompts 5–7). Optional second pass with gpt-5.4-pro on the three new ADRs only if that deployment is provisioned by then; not a blocker.
- **Files touched (anticipated, ±3):** ~40. New ADRs 0034/0035/0036; amendment to 0027 (response signing extension + multipart body-hash definition); `api/sbs_api/batch/{ingestion.py, validation.py, processing.py}`; `api/sbs_api/webhook/{signing.py, delivery.py, url_validation.py}`; new arq worker process `api/sbs_api/workers/batch_worker.py`; `api/sbs_api/models/{batch_files.py, webhook_deliveries.py, outbound_webhook_secrets.py, institution_webhook_configs.py}`; Alembic migration (adds tables above + `complaints.source` provenance column + `cert_thumbprint_required=true` on the two existing demo OAuth clients); `scripts/generate-synthetic-corpus.py`; `scripts/smoke-test-batch.sh`; `scripts/webhook-listener.py` (runs inside the `webhook-listener` docker-compose service); updates to `docker-compose.yaml` (arq `worker` service + `webhook-listener` service + shared volume `webhook-state` for the listener-ready file); `pyproject.toml` (arq + aiofiles + httpx async dependencies added in A0); 13 new test files; conformance check on test-fixture dependency overrides (closes a Prompt 7 Day-2 deferral).

---

## 1. Context and predecessor state

Prompt 7 closed Part 3 with a real auth chain end-to-end. The institution-facing API now stands up mTLS + OAuth + HMAC + rate-limiter against real client certs, signed requests, cert-bound JWTs, and per-institution token buckets. The five smoke-test-auth assertions pass end-to-end against the live API. 320 tests pass. The auth chain claim ("every request you see is mTLS-authenticated, HMAC-signed, OAuth-authorised, rate-limited, idempotent") is verifiable, not aspirational.

Prompt 8 closes Part 4 (Tier 2 batch ingestion + synthetic data). The institutional integration profile spans two tiers per ADR 0025 and the survey data: large banks running Tier 1 near-real-time, small COOPACs and financieras submitting Tier 2 batches because their core systems can't expose APIs. Prompt 8 builds the batch path with the same validation pipeline as Tier 1 (the proportional-treatment claim depends on this), adds outbound webhook signing for institution callbacks (the "we tell the institution when their batch completes" loop), and generates the synthetic complaint corpus that the May 25 demo and the Prompt 11 ML work both need.

The Prompt 7 retrospective named three concrete lessons that this spec applies:

1. **Run the smoke test against the live stack at every workstream boundary, not just at workstream G.** The uvicorn ASGI TLS extension gap cost 2.5 hours at hour ~12 because it was only discovered when end-to-end smoke testing ran. Prompt 8 inverts this: each workstream's exit gate is "smoke test passes against the live stack," not "unit tests pass against injected fixtures."
2. **Test-fixture conformance check is a Prompt 8 sub-workstream, not Day-2.** The `dependency_overrides` blanket-override blind spot from Prompt 7's second-opinion review is a real defect class. It lands as workstream F.1 with its own ADR amendment.
3. **No squash-merge for multi-workstream PRs.** Per the post-Prompt-7 conversation with the WBG technical lead, the repo default for multi-workstream PRs is now rebase-merge. This spec assumes that's in place; if it isn't, the maintainer toggles it before opening the PR.

The Prompt 7 closeout journal named nine carry-forwards. Of those, two are in Prompt 8 scope (`cert_thumbprint_required` seeding for demo clients; the test-fixture conformance check). The remaining seven stay deferred to their named targets (Part 6, Part 9, etc.).

Locked decisions going in:

- arq for async batch processing. APScheduler stays for the idempotency sweep (already in production). arq runs as a separate worker process in docker-compose.
- Outbound webhook signing primitive lands here; the SDK verification recipe is documented in markdown for Prompt 9 to polish. Institutions cannot yet verify our callbacks cleanly without writing their own verification code; this is acceptable for a sandbox and documented.
- Synthetic corpus is Tier 2 fidelity (structurally valid, realistic narratives, realistic monetary amounts, format-valid synthetic phone/document IDs). Tier 3 (statistically-realistic distributions for pattern detection) is a Prompt 11 augmentation hook.
- Full harness. Pre-draft GPT pressure-test on the spec in a fresh Claude.ai chat is non-optional. Cross-review at closeout uses gpt-5.4 on the full staged diff (same backend, same cost profile, same model as Prompt 7's review which surfaced six real findings on the three security ADRs). Optional second pass with gpt-5.4-pro on just the three new ADRs if that deployment exists in the tenancy by then.

---

## 2. Scope and boundary

### In scope (must-land, core)

1. **Tier 2 batch ingestion endpoint.** `POST /v1/batches` accepts a signed multipart upload (manifest JSON + CSV file). Manifest declares `reporting_period_start`, `reporting_period_end`, `row_count_submitted`, `checksum_sha256` of the CSV. The endpoint streams the multipart parts and rejects with 413 `BATCH_FILE_TOO_LARGE` if the CSV exceeds `SBS_API_MAX_BATCH_FILE_BYTES` (default 50 MB ≈ 50,000-100,000 rows at typical Anexo 1-A row size; configurable). Returns 202 Accepted with a `batch_id` and `Location` header pointing at `GET /v1/batches/{batch_id}`. The upload itself is mTLS + HMAC + OAuth (scope `batch:upload`) per Prompt 7's auth chain. CSV stays in object storage (sandbox: local filesystem at `data/batches/`; production: Azure Blob deferred to Part 9). The Alembic migration also adds a `complaints.source` column (enum: `api_realtime | batch`) — Tier 1 POST writes `api_realtime`, the Tier 2 worker writes `batch`, populated from this prompt forward (existing Tier 1 rows backfill to `api_realtime` in the migration).
2. **arq worker for async batch processing.** New process in docker-compose (`sbs-suptech-sandbox-worker-1`). Picks up `process_batch` jobs from Redis. Per batch: download CSV → validate each row through the *same* Pydantic validation pipeline as Tier 1 (`api/sbs_api/models/anexo_1a.py`) → for each valid row, INSERT a complaint identical to a Tier 1 POST result → for each invalid row, record the rejection in a `batch_row_rejections` table → update batch status to `complete` with `row_count_accepted` and `row_count_rejected`. Retries on transient failures (Postgres connection drop, etc.) with exponential backoff. Dead-letter after 5 retries with batch status `failed` and a structlog event.
3. **Batch status endpoint.** `GET /v1/batches/{batch_id}` returns the manifest plus current state (`pending` | `processing` | `complete` | `failed`), row counts, and (if `complete` or `failed`) a paginated link to row-level rejection details at `GET /v1/batches/{batch_id}/rejections`. Per-tenant binding per Prompt 6.
4. **Outbound webhook signing + delivery.** When a batch transitions to `complete` or `failed`, the worker enqueues a webhook delivery to the institution's registered callback URL. Payload is JSON; signature is HMAC SHA-256 over `<HTTP-method>\n<callback-path>\n<timestamp>\n<body-hash>\n<institution_id>` using a per-institution *outbound* secret distinct from the inbound HMAC secret. Headers: `X-SBS-Timestamp`, `X-SBS-Signature: hmac-sha256-v1=<base64>`, and `X-SBS-Key-Id` (value `sandbox-v1` from day one, mirroring the OAuth `kid=sandbox-v1` pattern from Prompt 7). The `outbound_webhook_secrets` table has a `kid` column so future rotation can store `active` + `previous` secrets keyed by `kid`; the rotation reader logic itself lands with the Part 8 admin work. Delivery retries with exponential backoff: 30s, 2min, 10min, 1hr, 6hr (5 attempts total, ~7.7-hour window). The webhook is the *convenience* layer; `GET /v1/batches/{batch_id}` is the *correctness* layer — institutions that miss the webhook (weekend outage, etc.) recover by polling. Default policy is no auto-disable on persistent delivery failure; the disable/re-enable admin path lands in Part 8. Persistent failures recorded in `webhook_deliveries` with status `delivery_failed`.
4a. **Webhook URL config + SSRF protection.** New table `institution_webhook_configs` (per-institution). Columns: `institution_id`, `callback_url`, `created_at`, `enabled`. (`event_type` deliberately NOT added — YAGNI; reintroduce in Prompt 12 when agent events actually need event-type routing.) The webhook delivery module validates the URL before each attempt: (a) scheme must be HTTPS (reject `http://`); (b) host must be FQDN (reject bare hostnames and IP literals); (c) host must resolve to a public IP (reject RFC 1918 private ranges, link-local, loopback, AWS metadata service IP `169.254.169.254`). Failing validation marks the delivery `delivery_failed` with `code=WEBHOOK_URL_REJECTED` and a structlog event; no retry. SBS analysts register URLs out-of-band (admin-API in Part 8). The sandbox seeds the three demo institutions' callback URLs to `http://webhook-listener:8080/sbs-callback` — a docker-compose service name resolving inside the compose network. This URL fails all three checks above (non-HTTPS, bare hostname, private IP after Docker resolution); a single env var `SBS_API_ALLOW_INSECURE_WEBHOOK_URLS=true` bypasses **all three** validation checks. The override is gated to `environment in {test, dev}`; it is refused with a startup-time error if `environment in {staging, prod}` is set. The webhook listener itself runs as a docker-compose service `webhook-listener` (added to `docker-compose.yaml` in workstream A); the readiness file is written to a shared docker volume that `smoke-test-batch.sh` polls from the host. This keeps the listener inside the compose network (matching the seeded URL) while letting host-side bash poll on readiness.
5. **Synthetic corpus generator + golden sample.** `scripts/generate-synthetic-corpus.py`. Produces ~10,000 complaints across 3 demo institutions (BANCO_DEMO_001, COOPAC_DEMO_002, plus FINANCIERA_DEMO_003 *created in this workstream*). Structurally valid Anexo 1-A. Peruvian Spanish narratives (~50 templates with parameter substitution; not LLM-generated to keep the build deterministic and reproducible). Realistic monetary amounts (log-normal distribution over the actual Peruvian banking range). Format-valid synthetic phone numbers (`9XXXXXXXX` pattern) and document IDs (DNI: 8-digit, RUC: 11-digit with valid checksum). Random distribution over a 90-day window ending today. The full ~10k corpus is **not committed to git** (regenerable from `make corpus` with the deterministic seed). A 200-row-per-institution **golden sample** *is* committed at `data/synthetic-corpus-golden/` (~600 KB total) as a fast-test fixture and a visible record of what the generator produces. Templates live at `data/synthetic-corpus-templates.yaml` (committed); seed is committed via the `--seed` flag default (`2026`). `data/synthetic-corpus/` is gitignored. **FINANCIERA_DEMO_003 is created here, not in workstream A:** workstream E adds the institution row, the cert via `scripts/dev-ca.sh --add-cert FINANCIERA_DEMO_003`, the `institution_certificates` row, the `institution_secrets` row, the `oauth_clients` row with `cert_thumbprint_required=true`, and the `institution_webhook_configs` row.
6. **`cert_thumbprint_required` seeding for the two existing demo clients.** Closes the Prompt 7 Day-2 item. The Alembic migration in workstream A updates the seeded `oauth_clients` rows for BANCO_DEMO_001 and COOPAC_DEMO_002, setting `cert_thumbprint_required=true`. (FINANCIERA_DEMO_003 is created in workstream E with the flag set from the start — see scope item 5.) Verifies cert-binding is enforced for demo clients, not just spec'd. The OAuth token endpoint (Prompt 7) already enforces this when the column is `true`; the seeding closes the loop.

### In scope (sub-workstream, must-land)

7. **Test-fixture dependency-override conformance check.** Closes the Prompt 7 Day-2 second-opinion finding. A new test (`tests/test_fixture_conformance.py`) asserts that no test fixture uses `app.dependency_overrides` to bypass the OAuth scope dependency or the HMAC verification dependency unless the test file explicitly opts in via a `@pytest.mark.auth_bypass` marker. The marker is rejected at collection time for any test file outside an allowlist (`tests/test_auth_failure_handler.py`, `tests/test_health.py`, `tests/test_openapi_match.py` — health and OpenAPI tests legitimately skip auth; the failure-handler test exercises 401/403/429 paths). Other tests that need to bypass auth must request the bypass through a per-fixture explicit override that the conformance test inspects. The actual bypass mechanism is a typed pytest fixture that records why the bypass is needed; the conformance check reads the record. ADR 0028 amendment.

### In scope (operational hardening)

8. **Batch validation pipeline reuse.** The CSV row → Anexo 1-A validation must use the *exact same* Pydantic models as Tier 1. No parallel validation path. The proportional-treatment claim ("Tier 1 and Tier 2 land in the same downstream pipeline") depends on this; the test layer enforces it (`tests/test_batch_validation_uses_tier_1_models.py` imports the models and asserts identity, not equivalence).
9. **Sandbox storage hygiene.** `data/batches/` is gitignored (added if not present). CSV files older than 7 days are pruned by an APScheduler job sharing the same scheduler as the idempotency sweep from Prompt 7. The prune job emits a structlog event `batch.storage.pruned`. Production overlay uses object-store lifecycle policies; the sandbox prune is the dev-grade equivalent.
10. **Webhook delivery telemetry.** Each delivery attempt emits a structlog event `webhook.delivery.attempt` with `delivery_id`, `attempt_num`, `http_status` (or `connect_failed`), `latency_ms`, `next_retry_at` (or null on final attempt). On dead-letter, additional event `webhook.delivery.dead_letter` with full attempt history. This is non-droppable because workstream G's smoke test depends on observable retry behaviour.

### In scope (closes named Prompt 7 deferrals)

- **`cert_thumbprint_required` seeding** — see scope item 6 above.
- **Test-fixture conformance check** — see scope item 7 above.

### Explicitly NOT in scope (defer with reason)

- **SDK stubs for webhook verification.** Outbound signing primitive lands here; language-specific verification helpers (Python, TypeScript) land in Prompt 9 as part of the developer portal completion.
- **Object storage migration (Azure Blob).** Sandbox uses local filesystem; production overlay uses Blob. Deferred to Part 9.
- **Webhook delivery dashboard for SBS analysts.** UI-facing surfacing of failed deliveries is Part 8 onboarding UI work; the data model and the structlog stream are in this prompt, the visualisation is not.
- **Real-time CSV streaming validation.** The worker downloads the CSV fully before validating. A streaming approach (validate-while-uploading for very large files) is a Part 9 optimisation.
- **Batch row deduplication across batches.** If the same complaint_id appears in two batches submitted a day apart, both are accepted; the second is detected at the Tier 1 idempotency layer (UNIQUE constraint on `complaint_id`) and recorded as a row rejection. Cross-batch dedup logic is deferred — the database constraint is the bridge.
- **Statistically-realistic complaint distributions (Tier 3 synthetic).** The generator hook is in place via a `--distribution-profile` flag (default: `uniform`); the `pattern-cluster` profile that injects detectable agent-relevant patterns is a Prompt 11 augmentation.
- **All seven other Prompt 7 Day-2 deferrals** (RFC 8705 base64url, JWT kid resolver, Lua clock source, etc.) — stay at their named targets.

---

## 3. Hour-9 time-box

**Structural rule, one hour tighter than Prompt 7.** The Prompt 7 retrospective showed that hour 10 was already too late — the runtime debug pushed wall-clock to ~12.5 hours including the squash-merge recovery. Prompt 8 is structurally similar (multi-workstream, auth-chain-dependent, end-to-end smoke test required) so the time-box compresses.

At wall-clock hour 9 from session start, the session does the following before any further work:

1. Open `/tmp/prompt-08-status.md` and write the current status.
2. If **workstreams A (batch endpoint), B (worker), C (status endpoint), D (webhook signing) are complete and the batch smoke test passes**, proceed to G (smoke-test extension) and H (closeout). Drop E (synthetic corpus) and F.1/F.2 (hardening) to a Prompt 8.5 follow-up PR. F.3 (webhook telemetry) stays even at hour-9 because G depends on it.
3. If **synthetic corpus generation (workstream E) is the only remaining core work**, run it (~30 min) and proceed to closeout. The corpus is demo-critical for May 25; it stays in even when hardening drops.
4. If **A, B, C, or D is materially incomplete at hour 9**, write `ABORTED: <reason>` to the status file. Do not proceed to closeout. Do not open a PR. The maintainer triages on return.

**"Complete" means "code written, tests passing, AND workstream exit-gate smoke test green against the live stack."** Not "code written, unit tests green against injected fixtures." This is the Prompt 7 lesson made spec-resident: the uvicorn ASGI TLS gap was invisible to fixture-based tests but obvious to a live-stack smoke check. Each workstream's exit gate names a specific live-stack assertion; the abort rule is triggered when that assertion has not been verified.

The hour-9 rule does not apply to workstream H (closeout) — closeout runs to completion regardless of clock.

Drop order if running late, in this exact order: F.2 (storage prune) → F.1 (conformance check) → E (synthetic corpus, only if A/B/C/D unsafe to ship without it). F.3 (webhook delivery telemetry) is **non-droppable** because workstream G's smoke test depends on observable retry behaviour against the canonical event schema.

---

## 4. Workstream order

The order is load-bearing — B depends on A's batch-files table, C depends on A and B, D depends on B's completion-event hook, E is independent and can run last, F items have their own dependencies.

**A0 — ADRs and amendments first + dependency adds, single commit.** All three new ADRs (0034, 0035, 0036) and one amendment (0027 response-signing extension + multipart body-hash definition) land as a single commit at the head of the branch. **Same commit also adds runtime dependencies to `pyproject.toml`:** `arq`, `aiofiles`, `httpx` (async client for webhook delivery), and updates `uv.lock`. The arq client API needs to be importable from workstream A's route handler, not just B's worker — so the dependency lands here, before A starts. ~50 minutes.

**A — Tier 2 batch ingestion endpoint.** New SQLAlchemy models (`batch_files`, `batch_row_rejections`). Alembic migration that also: adds the `complaints.source` column (backfills existing rows to `api_realtime`), creates `institution_webhook_configs`, creates `outbound_webhook_secrets` (with `kid` column), creates `webhook_deliveries`, sets `cert_thumbprint_required=true` on the two existing demo OAuth clients (BANCO_DEMO_001, COOPAC_DEMO_002), seeds webhook configs for those two institutions pointing at the docker-compose webhook listener. Route handler at `POST /v1/batches` accepting multipart with manifest JSON + CSV file. Multipart streaming with size cap (`SBS_API_MAX_BATCH_FILE_BYTES`, default 50 MB; 413 `BATCH_FILE_TOO_LARGE` on overflow with `X-Correlation-Id` and `traceparent` per ADR 0028). Manifest validation (period dates, row count expectation, SHA-256 of file matches `checksum_sha256` claim). On success: persist batch metadata, write CSV to `data/batches/<batch_id>.csv`, enqueue arq job, return 202 with Location header. OpenAPI spec updated with the new endpoint plus schemas; Spectral clean. **Exit gates (all live-stack): (a) `bash scripts/smoke-test-batch.sh stage-a` confirms 202 with valid Location and a batch row in `state=pending`; (b) oversized upload returns 413 with both observability headers; (c) Spectral 0 errors on `api/openapi/sbs-api-v1.yaml`.** 2.5-3 hours.

**B — arq worker for async batch processing.** New `api/sbs_api/workers/batch_worker.py`. arq settings, Redis connection, job handler `process_batch(batch_id)`. **First step of B is integration de-risk** (~15 min before writing the job handler): bring up the arq worker container in isolation, confirm it connects to Redis, register and dispatch a no-op job, confirm it completes. Catching arq/Redis/docker-compose integration friction here costs minutes; catching it at the end of B (Prompt 7 pattern) costs hours. The docker-compose `worker` service inherits the API service's env block via a YAML anchor (`x-api-env: &api-env`) so DATABASE_URL, REDIS_URL, SBS_API_ENVIRONMENT, structlog config, and the `SBS_API_ALLOW_INSECURE_WEBHOOK_URLS` gate all match the API service — preventing the worker from behaving differently from the API on URL validation or any other env-gated logic. Worker logic after de-risk: load batch metadata → read CSV → for each row, validate via Tier 1 Pydantic models (shared import asserted by `test_batch_validation_uses_tier_1_models.py` in this workstream, *not* in F — the test lives where the worker code that imports the models lives) → on valid, INSERT complaint row with `source=batch` (sharing the Tier 1 INSERT path via a refactored helper); on invalid, INSERT into `batch_row_rejections` with the Pydantic error detail. Update batch status to `complete` with final counts. Emit structlog `batch.processing.completed`. docker-compose service for the worker. **Exit gate (live-stack): upload a 100-row test CSV via `bash scripts/smoke-test-batch.sh stage-b`, worker processes it, batch transitions to `complete`, complaints visible via Tier 1 GET endpoint with `source=batch`.** 2.5-3 hours.

**C — Batch status endpoint.** `GET /v1/batches/{batch_id}` with per-tenant binding. Returns manifest + state + row counts + (when complete/failed) link to `/rejections`. `GET /v1/batches/{batch_id}/rejections` with cursor pagination (reuses the signed cursor primitive from Prompt 7's ADR 0028 amendment). OAuth scope `batch:upload` required (no separate read scope; if you can upload, you can read your own batches' status). OpenAPI spec updated; Spectral clean. **Exit gates (live-stack): (a) `bash scripts/smoke-test-batch.sh stage-c` confirms status visible immediately after upload and updates as worker processes; (b) Spectral 0 errors.** 1.5 hours.

**D — Outbound webhook signing + delivery + URL validation.** Signing module `api/sbs_api/webhook/signing.py` reuses the inbound HMAC canonical-request shape with `<HTTP-method>\n<callback-path>\n<timestamp>\n<body-hash>\n<institution_id>` — same five lines, different secret namespace, `X-SBS-Key-Id: sandbox-v1` added. URL validation module `api/sbs_api/webhook/url_validation.py` enforces all three checks (HTTPS-only, FQDN-only, no private/loopback/link-local IPs, no AWS metadata service IP); bypassed only when `SBS_API_ALLOW_INSECURE_WEBHOOK_URLS=true` AND `environment in {test, dev}`. Delivery worker job `deliver_webhook(delivery_id)` enqueued from the batch worker on completion. Retry with exponential backoff (30s/2min/10min/1hr/6hr). **Exit gate (live-stack): `bash scripts/smoke-test-batch.sh stage-d` — signed callback fires to the listener container, signature validates correctly with `X-SBS-Key-Id` present, retry observable via test that returns 500 then 200, URL pointing at private IP is rejected when the dev override is off.** 2-2.5 hours.

**E — Synthetic corpus generator + FINANCIERA_DEMO_003 creation + golden sample.** Sequence within E: (1) create FINANCIERA_DEMO_003 — extend `scripts/dev-ca.sh` with `--add-cert FINANCIERA_DEMO_003`, add institution row, `institution_certificates` row, `institution_secrets` row, `oauth_clients` row with `cert_thumbprint_required=true`, `institution_webhook_configs` row. (2) Write `scripts/generate-synthetic-corpus.py`: Anexo 1-A schema awareness via Pydantic model introspection; ~50 narrative templates in Peruvian Spanish loaded from `data/synthetic-corpus-templates.yaml`; deterministic seeding (`--seed` flag, default `2026`); per-institution CSV files + matching manifests to `data/synthetic-corpus/`; `--distribution-profile` flag with `uniform` default; `pattern-cluster` stub raises `NotImplementedError` with a "lands in Prompt 11" message. (3) Generate the 200-row-per-institution golden sample, commit to `data/synthetic-corpus-golden/`. (4) Make target `make corpus` regenerates the full ~10k corpus. **Exit gate (live-stack): `bash scripts/smoke-test-batch.sh stage-e` — generate corpus, upload one full batch from FINANCIERA_DEMO_003 (newest cert), batch processes cleanly, 100% acceptance rate (all rows structurally valid).** 1.5-2 hours.

**F — Hardening + conformance check.** Three items, each its own commit. F.1 test-fixture conformance check (~45 min), F.2 batch storage prune job (~30 min — APScheduler entry deletes `data/batches/*` older than 7 days, structlog event), F.3 webhook delivery telemetry (~20 min — canonical structlog event schema `webhook.delivery.attempt` with named fields `delivery_id`, `attempt_num`, `http_status`, `latency_ms`, `next_retry_at`; plus `webhook.delivery.dead_letter` with full attempt history on final failure; **non-droppable** because workstream G's smoke test asserts retry observability against this exact schema). Drop order at hour-9: F.2 → F.1. F.3 stays. 1-1.5 hours if everything lands. (The validation-identity test lives in workstream B per §6, not here — B's worker is where the shared Pydantic import naturally lives.)

**G — Batch smoke test extension.** `scripts/smoke-test-batch.sh`. New end-to-end test exercising: corpus generation → mTLS+HMAC+OAuth-signed multipart upload → 202 returned with Location → polling batch status until `complete` → webhook callback fires to the long-running `webhook-listener` compose service (which logs each receipt as `PASS` or `FAIL` per signature verification) → smoke script tails the listener log and asserts the expected PASS line is present → batch listed via status endpoint with correct counts → row-level rejections paginated correctly when invalid rows are present → URL-validation rejection path verified by attempting delivery to a private IP. The listener container writes `/webhook-state/ready` when bound; the shared docker volume `webhook-state` is mounted at `./webhook-state/` on the host; `smoke-test-batch.sh` polls for `./webhook-state/ready` with a 5-second timeout before triggering the upload (prevents the race condition where the worker fires the callback before the listener is bound). Stage flags (`stage-a`, `stage-b`, `stage-c`, `stage-d`, `stage-e`, `stage-g-full`) let each workstream's exit gate invoke only its slice. **Exit gate: `stage-g-full` passes against live stack with all assertions, including signature verification and retry observability.** 1 hour.

**H — Closeout.** Six subagent passes + cross-review on the full staged diff (gpt-5.4). Optional second pass on the three new ADRs only with gpt-5.4-pro if that deployment is provisioned; not blocking. Second-opinion adversarial. Typed approval. ~60-90 minutes.

---

## 5. ADRs to land

### ADR 0034 — Batch ingestion architecture and worker model (Accepted)

**Decision.** Tier 2 batch ingestion uses an asynchronous worker pattern: the API endpoint accepts the upload, persists the file, and enqueues a job; an arq worker process picks up the job and runs the same Tier 1 validation pipeline row-by-row. The endpoint returns 202 Accepted; the institution polls the status endpoint or receives a webhook callback on completion. arq (not Celery, not RQ, not FastAPI BackgroundTasks, not APScheduler, not just-Redis-Streams) for the worker. Multipart upload with size cap (`SBS_API_MAX_BATCH_FILE_BYTES`, default 50 MB). CSV stored in object storage (sandbox: local filesystem; production: Azure Blob deferred to Part 9). Per-row validation uses the *exact same* Pydantic models as Tier 1; no parallel validation path. Concurrent batches from the same institution process serially per the arq worker's single-queue FIFO; per-institution queue partitioning is a Part 9 production concern.

**Why arq specifically, not the alternatives.** FastAPI BackgroundTasks runs in the same event loop and offers no durability — a uvicorn restart loses the in-flight batch, which is not acceptable for a regulator system. APScheduler is cron-shaped (run-every-N-minutes), not queue-shaped (pick up jobs as they arrive) — using it for batch dispatch would mean hacking its trigger system. Celery and RQ are mature alternatives but heavier; arq is purpose-built for asyncio Python (matches the stack) and uses Redis (already a dependency). The production-path alignment matters: demonstrating an async worker pattern in the sandbox lets SBS point at the architecture rather than handwave at "we'd add workers later."

**Precedent (one solid).** arq's documentation (the canonical use case described in the arq README) and FastAPI's own deployment recipe for arq workers are the implementation reference. The architectural pattern — HTTP endpoint enqueues, async worker drains, status endpoint exposes state, webhook signals completion — is the regulator-domain default for batch ingestion: Open Banking UK's batch-submission flow follows the same shape, as does the SEC's EDGAR filing submission system. Cited in `docs/research/market-comparators.md` §5.B (Event-driven ingestion layer); the §5.B subsection is extended in this prompt to cover the worker-process variant alongside the streaming variant, with a specific subsection on async-worker patterns for regulator data ingestion.

**Consequences.** Worker process is a new operational surface in docker-compose. Sandbox prune job manages local-filesystem hygiene; production lifecycle policies replace it in Part 9. Same-validation-as-Tier-1 invariant is test-enforced (`test_batch_validation_uses_tier_1_models.py` asserts class identity, not just equivalence). Dead-letter surfacing in the sandbox is "grep structlog for `batch.processing.failed`"; a Part 8 admin UI exposes dead-lettered batches to SBS analysts directly. Both `process_batch` and `deliver_webhook` jobs share the same arq worker process and queue, so a long-running batch can delay a queued webhook delivery for an earlier batch's completion — FIFO behaviour is sandbox-acceptable but worth knowing for live demo timing (don't trigger two batches concurrently in the demo flow).

### ADR 0035 — Outbound webhook signing contract (Accepted)

**Decision.** When the API calls back to an institution (batch completion, batch failure, future agent-triggered events), the call is signed with HMAC SHA-256 using a per-institution outbound secret distinct from the inbound HMAC secret. Canonical request shape mirrors ADR 0027's inbound contract: five lines (method / callback-path / timestamp / body-hash / institution_id). Headers: `X-SBS-Timestamp`, `X-SBS-Signature: hmac-sha256-v1=<base64>`, and `X-SBS-Key-Id` (value `sandbox-v1` from day one, mirroring the OAuth `kid=sandbox-v1` pattern from Prompt 7). The `outbound_webhook_secrets` table has a `kid` column to enable future rotation (active + previous secrets keyed by `kid`) without an additional migration; the rotation reader logic itself is deferred to Part 8 admin work. Same 5-minute skew tolerance as inbound. Delivery retries with exponential backoff: 30s, 2min, 10min, 1hr, 6hr (5 attempts total, ~7.7-hour window). Persistent failures recorded in `webhook_deliveries` with status `delivery_failed`. Default policy is no auto-disable on persistent failure — the disable/re-enable admin path lands in Part 8.

**Webhook URL validation.** The callback URL is per-institution and stored in `institution_webhook_configs`. Before each delivery attempt the URL is validated against three checks: (a) HTTPS-only (no `http://`); (b) FQDN host (no bare hostnames, no IP literals); (c) host resolves to a public IP (RFC 1918 private ranges, link-local, loopback, and AWS metadata service IP `169.254.169.254` are rejected). Validation failures mark the delivery `delivery_failed` with `code=WEBHOOK_URL_REJECTED` and emit a structlog event; no retry. The sandbox seeds demo institutions' callback URLs to the docker-compose `webhook-listener` service. A single env var `SBS_API_ALLOW_INSECURE_WEBHOOK_URLS=true` bypasses **all three** checks (the name signals the breadth of the override; an earlier draft used a narrower `ALLOW_PRIVATE_WEBHOOK_URLS` name which was misleading since the seeded URL also fails the HTTPS and FQDN checks). The override is itself gated to `environment in {test, dev}` — startup refuses to boot if it is set with `environment in {staging, prod}`.

**Webhook as convenience, polling as correctness.** The webhook is the *convenience* layer; `GET /v1/batches/{batch_id}` is the *correctness* layer. An institution (e.g., a COOPAC risk officer (illustrative)'s 12-person COOPAC) that misses the webhook due to a weekend outage recovers by polling the status endpoint. The 7.7-hour retry window is acceptable on that basis — it would be too short if the webhook were the only delivery mechanism, but it isn't. This framing is what makes the retry policy defensible against the "Stripe retries for 3 days" pushback.

**Precedent (one solid).** Stripe webhooks documentation describes the canonical pattern: HMAC signing, timestamp + signature headers, replay-resistant by timestamp window, exponential-backoff retry, persistent failure recording. Cited in `docs/research/market-comparators.md` §5.A.M (extended for outbound flows). Stripe's auto-disable-after-extended-failure pattern is documented but not adopted in the sandbox; the admin-disable surface in Part 8 is the equivalent.

**Consequences.** Institutions must implement signature verification on their callback receiver. Verification recipe documented in markdown alongside this prompt; language-specific SDK helpers (Python, TypeScript) land in Prompt 9 as part of the developer portal completion. Outbound secrets rotate independently of inbound; rotation procedure (with the `kid` column already in place) is operator-driven via Part 8 admin-API. The 5-attempt retry window is sandbox-shaped; production may extend it to match Stripe's 3-day pattern once SBS operations confirms what is realistic for institutional uptime profiles.

### ADR 0036 — Synthetic data corpus fidelity tiers (Accepted)

**Decision.** Three fidelity tiers for synthetic Anexo 1-A complaint data. Tier 1: structurally valid only. Tier 2: tier 1 plus realistic Peruvian Spanish narratives (template-based with parameter substitution), realistic monetary amounts (log-normal over the actual banking range), format-valid synthetic phone numbers and document IDs (DNI 8-digit, RUC 11-digit with valid checksum). Tier 3: tier 2 plus statistically-realistic distributions for pattern detection. Prompt 8 ships Tier 2; Tier 3 hooks via `--distribution-profile` are stubbed for Prompt 11. Deterministic seeding for reproducibility. Templates in YAML, not LLM-generated, for build-determinism and audit-friendliness.

**Tier 3 patterns (sketched here so Prompt 11 inherits a concrete spec, not a name).** The Tier 3 generator will inject at minimum: (a) heavy-tail complaint frequency per institution (Pareto-shaped, so 80% of complaints concentrate in 20% of institutions); (b) weekly seasonality with Friday peak (consumer-banking complaint patterns; matched against the SBS Conduct department head's conduct-supervision view); (c) correlated complaint clusters following synthetic operational incidents (e.g., 200 complaints about a single mortgage product over 10 days, simulating an institution-level conduct failure); (d) prudential-vs-conduct pattern distinction — prudential patterns concentrate by counterparty/exposure (sparse but high-impact, matching the SBS Conduct department head's prudential lens), conduct patterns spread across many consumers (dense but lower per-incident impact). Tier 3 is what makes the Prompt 12 agent demo non-trivial; without it, the agents reason over uniform noise and produce uninteresting outputs.

**Corpus storage: golden sample committed, full corpus regenerated.** A 200-row-per-institution golden sample (~600 KB) is committed to `data/synthetic-corpus-golden/` for fast-test fixtures and PR-visible record of what the generator produces. The full ~10k corpus is *not* committed; it regenerates from `make corpus` with the deterministic seed. Templates and seed *are* committed. This avoids 10 MB of generated-artifact bloat in git history while preserving reproducibility (the script is deterministic) and reviewability (the golden sample shows the data shape).

**Precedent (one solid).** The CFPB Consumer Complaint Database publishes anonymised real complaints with realistic narratives and structurally-valid metadata; their data-fidelity choices (preserving narrative realism, preserving distribution shape, anonymising PII) are the regulator-domain precedent for what "demo-credible synthetic complaint data" looks like. Cited in `docs/research/market-comparators.md` §2.1 (extended for synthetic-corpus generation, including a Tier-3-patterns subsection enumerating the four pattern types above).

**Consequences.** Templates are an audit surface — a contributor adding inappropriate content to the template file is detectable in PR review. Tier 3 is a Prompt 11 augmentation; agents in Prompt 12 will rely on Tier 3 patterns being injectable. The deterministic seed plus committed templates plus the `make corpus` target give any contributor (or any reviewer at WBG or SBS) the ability to regenerate the exact corpus used in any prior demo, given the seed. Template changes that materially alter the corpus shape are visible in the git diff of the templates file, not in a 10 MB CSV diff that would have been rubber-stamped.

### ADR 0027 amendment — response-signing extension + multipart body-hash definition

**Outbound response signing.** The same canonical request shape applies in both directions: five lines (method / path / timestamp / body-hash / institution_id), `hmac-sha256-v1=` prefix. Inbound uses per-institution *inbound* secret (`institution_secrets`); outbound uses per-institution *outbound* secret (`outbound_webhook_secrets`). The two are stored in separate tables to support independent rotation; both have a `kid` column to enable rolling-secret rotation in the future (currently `kid=sandbox-v1` everywhere). Both share the 5-minute clock skew tolerance and the 24-hour replay window (the outbound side does not enforce replay protection on the receiving institution's behalf — that is the institution's responsibility per their verification recipe).

**Multipart body-hash definition (inbound).** For `POST /v1/batches` (and any future multipart endpoint), the `body-hash` line of the canonical request is the **SHA-256 of the CSV file bytes only**, not the SHA-256 of the multipart envelope or the manifest JSON. Rationale: the manifest declares the CSV's `checksum_sha256` as an independently-verifiable field that the server compares against the actually-received bytes, so the manifest hash is redundant as a signing input. Signing the CSV bytes directly means the institution's signing client computes one hash (over the file they're uploading) and the server's verifier computes the same hash on receipt — the multipart boundary encoding does not affect the signature. The `Content-Length` of the multipart envelope is *not* part of the canonical request because boundary length is implementation-detail-dependent.

**`X-SBS-Key-Id` header.** Both inbound and outbound requests include `X-SBS-Key-Id` alongside `X-SBS-Timestamp` and `X-SBS-Signature`. Value is `sandbox-v1` from day one. The server selects the secret to verify against by `kid` lookup, not by trial-decryption. Future rotation rolls in a new `kid` (e.g., `sandbox-v2`); the previous secret stays valid in the `active` slot until cutover, then is moved to `previous` for the grace window, then retired.

---

## 6. Tests required

Cumulative target: 320 → ~380 tests (13 new files, ~50-60 test cases at typical density).

**Workstream A — batch endpoint:**
- `tests/test_batch_endpoint.py` — happy path 202, manifest validation, checksum mismatch → 400, missing file → 400, oversized file → 413, mTLS+HMAC+OAuth scope `batch:upload` enforced.
- `tests/test_batch_multipart_streaming.py` — multipart size cap fires before full buffer; canonical-request HMAC verification works against multipart body hash (CSV bytes only, per ADR 0027 amendment).
- `tests/test_complaints_source_backfill.py` — post-migration assertion: all pre-existing complaints have `source='api_realtime'`; new Tier 1 POST writes `api_realtime`; new Tier 2 batch row writes `batch`. Three assertions, five lines of test logic.

**Workstream B — arq worker:**
- `tests/test_batch_worker.py` — testcontainers + arq worker subprocess; submits a batch, polls status, asserts `complete`; submits batch with mixed valid/invalid rows; asserts row counts and rejection details.
- `tests/test_batch_validation_uses_tier_1_models.py` — imports validation function; asserts the Pydantic model class identity is the *same object* as Tier 1's; refactor-resistant test.
- `tests/test_batch_worker_retries.py` — simulates Postgres connection drop mid-processing; asserts retry with exponential backoff; asserts dead-letter after 5 attempts.

**Workstream C — batch status:**
- `tests/test_batch_status_endpoint.py` — happy path, per-tenant binding (cross-tenant returns 404), state transitions visible.
- `tests/test_batch_rejections_pagination.py` — signed cursor pagination works on rejection list; tampered cursor → 400 CURSOR_INVALID.

**Workstream D — webhook signing:**
- `tests/test_webhook_signing.py` — canonical-request shape correct for outbound; signature deterministic given inputs; constant-time compare.
- `tests/test_webhook_delivery.py` — testcontainers + Python listener; happy path delivery; signature verifies; retry on 500 then success on 200; dead-letter after 5 attempts; structlog events at each step.

**Workstream E — synthetic corpus:**
- `tests/test_synthetic_corpus_generator.py` — deterministic given seed; 100% Anexo 1-A schema compliance; narrative templates render correctly; DNI/RUC checksums valid; monetary distribution within expected range.

**Workstream F — hardening:**
- `tests/test_fixture_conformance.py` — the conformance test itself, as described in §2 item 7.
- `tests/test_batch_storage_prune.py` — prune job deletes files older than 7 days; emits structlog event.

---

## 7. Smoke test extension

`scripts/smoke-test-batch.sh`. Sequence: bring up stack (including the `webhook-listener` compose service) → poll `./webhook-state/ready` with a 5-second timeout to confirm the listener is bound → generate 100-row synthetic CSV → upload as authenticated batch → poll status until `complete` → tail the listener log (`docker compose logs webhook-listener`) and assert the expected `PASS` line is present for the signature verification → assert row counts match → exercise the URL-validation rejection path by attempting a delivery to a private-IP-resolving callback (with the dev override off). Exits non-zero on first failed assertion. Reuses the auth-chain primitives from `smoke-test-auth.sh` (cert paths, OAuth token retrieval, HMAC signing).

`scripts/webhook-listener.py` runs as a **long-running** server inside the `webhook-listener` compose service. On bind it writes `/webhook-state/ready` (the shared volume mount inside the container). For each received webhook it verifies the HMAC signature using the outbound secret and logs one line: `PASS delivery_id=<id>` on signature match, `FAIL delivery_id=<id> reason=<...>` on mismatch. The smoke script asserts log contents rather than the process-exit code, because the listener must stay running across multiple stages (`stage-d` retry test, `stage-g-full` URL-validation rejection path). Bash + Python because the signature verification is cleaner in Python and stays consistent with what the SDK recipe will document.

---

## 8. Pre-flight checklist

```bash
# 1. Clean main, 320 tests pass.
git checkout main && git pull && uv run pytest -q  # expects "320 passed"

# 2. Spectral clean on OpenAPI.
./node_modules/.bin/spectral lint api/openapi/sbs-api-v1.yaml

# 3. Docker stack down, volumes optionally wiped.
docker compose down  # or: docker compose down -v for clean slate

# 4. TLS bundle env vars resolved.
echo $SSL_CERT_FILE && echo $REQUESTS_CA_BUNDLE
[ -f "$SSL_CERT_FILE" ] && echo "OK"

# 5. Cross-review reaches Azure OpenAI (gpt-5.4 baseline).
python scripts/cross_review.py --target CLAUDE.md

# 6. Optional deeper deployment check (does NOT block closeout — gpt-5.4 is the baseline).
if [ -z "$AZURE_OPENAI_DEPLOYMENT_DEEP" ]; then
  echo "AZURE_OPENAI_DEPLOYMENT_DEEP not set — closeout uses gpt-5.4 only (acceptable)"
else
  python scripts/cross_review.py --target CLAUDE.md --deployment "$AZURE_OPENAI_DEPLOYMENT_DEEP"
fi

# 7. caffeinate.
ps aux | grep "[c]affeinate" || echo "Start: caffeinate -dis &"

# 8. arq + aiofiles + httpx not yet on disk (added by A0, not pre-installed).
uv pip list | grep -E "(arq|aiofiles)" && echo "WARN: deps already present — verify versions match A0 intent" || echo "OK — A0 will add arq + aiofiles + httpx to pyproject.toml"

# 9. Branch.
git checkout -b part-04/tier-2-batch-and-synthetic-corpus

# 10. Pre-draft GPT pressure-test status.
echo "Confirm: spec pressure-tested in fresh Claude.ai chat before kickoff?"
```

---

## 9. Kickoff message

(For the Claude Code session, paste after the context bundle and the spec.)

```
You are executing Prompt 8 for the SBS Peru SupTech sandbox. Spec is in
your context. Execute in workstream order: A0 → A → B → C → D → E → F → G → H.
Hour-9 time-box rule in §3 is structural — one hour tighter than Prompt 7
based on the retrospective.

CRITICAL DISCIPLINE FROM PROMPT 7: each workstream's exit gate is "smoke
test passes against the live stack," not "unit tests pass against
injected fixtures." Bring up the stack early. Run smoke checks at each
workstream boundary. The uvicorn ASGI TLS extension gap cost 2.5 hours
last time precisely because end-to-end testing only happened at the end.

Before any code, read: api/sbs_api/middleware/, api/sbs_api/dependencies/,
api/sbs_api/routes/complaints.py (for the Tier 1 INSERT path B will share),
api/sbs_api/workers/ (if exists), docker-compose.yaml, scripts/smoke-test-auth.sh
(the pattern to extend), the auth ADRs 0031/0032/0033 plus 0027/0028/0029
amendments.

Commit cadence: one commit per workstream minimum. Commit messages follow
Conventional Commits.

Write /tmp/prompt-08-status.md at each workstream boundary and at hour 9.

If hour-9 fires with synthetic corpus still pending, run it anyway (~30
min) before closeout — corpus is demo-critical for May 25.

Closeout runs to completion regardless of clock.

caffeinate -dis is running. Begin with workstream A0.
```

---

## 10. Closeout protocol

**Cross-review pass (mandatory): gpt-5.4 on the full staged diff.**
`python scripts/cross_review.py --target $(git diff --staged --name-only) --slug tier-2-batch-and-synthetic-corpus` with default `AZURE_OPENAI_DEPLOYMENT` (gpt-5.4). Estimated cost: $0.10–0.50. This is the same backend and same call shape that surfaced six real findings on Prompt 7's three security ADRs — sufficient for Prompt 8's review needs.

**Optional second pass (nice-to-have, not blocking): gpt-5.4-pro on the three new ADRs only**, if `AZURE_OPENAI_DEPLOYMENT_DEEP=gpt-5.4-pro` is set in the environment. `python scripts/cross_review.py --target docs/adr/0034-batch-ingestion-architecture.md docs/adr/0035-outbound-webhook-signing-contract.md docs/adr/0036-synthetic-corpus-fidelity-tiers.md --slug tier-2-batch-and-synthetic-corpus-deep --deployment "$AZURE_OPENAI_DEPLOYMENT_DEEP"`. Estimated cost: under $1. If the deployment isn't provisioned, log the gap in the journal and skip — do not block closeout.

The Prompt 7 retrospective established that the bottleneck in review quality is *running the review at all*, not the model's reasoning depth. gpt-5.4 catches real findings cheaply; reasoning-model upgrades (o3-pro and similar) would add 20-50x cost for marginal additional findings on this class of ADR. Skipped in this spec on cost-benefit grounds; the lesson stands until evidence accumulates otherwise.

**Subagent passes:** all six on the staged diff. Standard.

**Second-opinion:** runs on the diff. Expected behaviour: WEAKNESS-FLAGGED on the outbound secret being stored adjacent to inbound (separate table is the mitigation, but operational rotation procedures are deferred to Part 8 admin); WEAKNESS-FLAGGED on the local-filesystem storage in sandbox (mitigation: ADR 0034 names Part 9 production migration). Both expected; both logged not blocked.

**Triage disposition** is mandatory on the cross-review file. If the second pass ran, both files get triaged.

**Typed approval gate.** No bypass.

---

## 11. Failure-mode guardrail

`/tmp/prompt-08-status.md` format identical to Prompt 7 but with the workstream list updated. Writes at every workstream boundary, at hour 9 mandatory, and on any unrecoverable error.

---

## 12. Definition of done

Part 4 closes when:

1. `POST /v1/batches` accepts signed multipart (with body-hash over CSV bytes only per ADR 0027 amendment), persists batch + file, enqueues worker job, returns 202 with Location. Oversized upload returns 413 with `X-Correlation-Id` and `traceparent`.
2. arq worker processes batches end-to-end using the same Pydantic validation as Tier 1; `complaints.source=batch` written for each row.
3. `GET /v1/batches/{batch_id}` and `/rejections` work with per-tenant binding and signed pagination.
4. Webhook callback fires on batch completion with valid HMAC signature, `X-SBS-Key-Id: sandbox-v1` header, and URL-validation rejecting private-IP callbacks; retries observable via structlog.
5. Synthetic corpus generates deterministically; FINANCIERA_DEMO_003 created with cert + secrets + webhook config; one batch from each of the three institutions uploads cleanly with 100% acceptance; golden sample committed to `data/synthetic-corpus-golden/`.
6. Conformance check on test-fixture overrides passes (closes Prompt 7 Day-2 deferral).
7. `cert_thumbprint_required=true` on all three demo OAuth clients (closes Prompt 7 Day-2 deferral).
8. Three new ADRs (0034, 0035, 0036) Accepted; ADR 0027 amended with both response-signing extension and multipart body-hash definition.
9. `scripts/smoke-test-batch.sh stage-g-full` passes end-to-end against live stack.
10. Test count: 320 → ~380.
11. Cross-review triage filled for both passes.
12. Typed approval gate clears.

---

## 13. Notes on what this prompt is and is not

This prompt is the second of the two ingestion paths. After Prompt 8, the proportional-treatment claim is real: a large bank with Tier 1 integration and a small COOPAC with Tier 2 batch submission both land complaints through the same validation pipeline. The downstream agents in Prompt 12 see the same Anexo 1-A shape regardless of origin.

This prompt is not the developer portal completion (that's Prompt 9), not the UI wiring (that's Prompt 10), not the ML substrate (that's Prompt 11), not the agents (that's Prompt 12). The webhook *primitive* lands here; the SDK to help institutions verify our webhooks lands in Prompt 9.

This prompt is also not the synthetic-data realism that the agent demo needs. The Tier 2 fidelity that lands here is enough for May 25 surface validation; the Tier 3 statistically-realistic patterns that make the Prompt 12 agents detect *something interesting* are deferred to Prompt 11. The `--distribution-profile` flag is the hook.

If on the morning of May 20 any pre-flight check fails, the maintainer triages before kicking off. The post-Prompt-7 retrospective lesson applies twice: smoke test against live stack at every workstream boundary, and rebase-merge (not squash) the multi-workstream PR.

---

End of Prompt 8 spec.
