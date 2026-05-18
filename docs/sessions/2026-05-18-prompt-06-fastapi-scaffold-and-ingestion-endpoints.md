# Session journal — 2026-05-18 — fastapi-scaffold-and-ingestion-endpoints

- **Date:** 2026-05-18
- **Prompt:** 6
- **Part:** 2 (closing)
- **Slug:** fastapi-scaffold-and-ingestion-endpoints
- **Branch:** `part-02/fastapi-scaffold-and-ingestion-endpoints`
- **Predecessor:** Prompt 5 (PR #27 post-closeout addenda on top of `5c95ec8` / PR #26).
- **Files touched:** 23 (12 new tests, 3 new ADRs, 1 new smoke script, middleware fix, fixture FK ordering fix, docs: PLAN.md, CONTRIBUTING.md, DECISIONS.md, adr/README.md, CLAUDE.md, pyproject.toml runtime+test deps).

---

## Cross-model review — triage line

Cross-review file: [docs/reviews/2026-05-18-fastapi-scaffold-and-ingestion-endpoints.md](../reviews/2026-05-18-fastapi-scaffold-and-ingestion-endpoints.md). Model: gpt-5.4 via Azure OpenAI WBG ITS tenancy.

Net disposition: two fixes applied in this prompt (startup-probe wording aligned across ADR 0030 and test docstring; `greenlet` runtime dependency documented in ADR 0028 §11). Seven items deferred to named future prompts:

- Prompt 7 — middleware-handler-rule ADR wording refinement; 413 path observability headers; full-body buffering on the slow path; idempotency concurrency policy (placeholder-insert-under-unique-constraint); replay-header safelist amendment to ADR 0029.
- Prompt 8 — smoke-test pinning (read configured max body size; pin tracing exporter mode); migration test schema isolation.
- Prompt 9 — OpenAPI examples test strict mode (lands with the conformance suite).

One item accepted as documented property (readiness cache is process-global per-worker; correct trade-off for the May 25 sandbox; documented in ADR 0030).

## Adversarial review

`second-opinion` subagent verdict: **WEAKNESS-FLAGGED** (does not block).

Strongest finding: the `pendiente → pendiente` self-edit transition in `api/sbs_api/state_machine/resolution_status.py` is admitted as a legal transition with the stated intent of supporting "notes-only" edits, but no ADR section enumerates which fields a no-op self-edit may mutate, and the route handler has no diff-capture hook for the audit log Part 3 will need. `etag_version` bumps will look identical for "status changed" vs "notes changed", erasing the ability to reconstruct *what* was edited from the row alone.

Disposition: tracked for Part 3 (audit log landing). Mitigation candidates: (i) drop the self-edit from `ALLOWED_TRANSITIONS` and route notes edits through a distinct `PATCH /complaints/{id}` endpoint with its own ADR, or (ii) keep the self-edit but add an ADR 0028 §9 sub-section enumerating which fields a self-edit may touch, and land a pre-Part-3 stub for an audit-event hook before the audit chain arrives. Choice deferred until the audit-log requirements are concrete.

Secondary finding (lower severity): cursor pagination is unsigned base64. Tenant filter prevents cross-tenant reads, so this is not an authorization bypass; the real risk is a malicious client forging cursors to skip records during a conformance run. Mitigation: HMAC the cursor payload with a server-side key. Tracked for Part 3 hardening.

## What landed

Part 2 closed. The canonical OpenAPI contract from Prompt 5 now has a live FastAPI implementation behind it. Institutions can hit `POST /v1/complaints` with curl, receive a 201 with an ETag and a fetchable `Location` URL, see the row in Postgres, retrieve it, list with cursor pagination, transition its resolution status under ETag concurrency control, and submit batch manifests. All nine endpoints from the spec are wired. The runtime fails closed when authentication is not configured (the foot-gun mitigation): with `AUTH_STUB_ENABLED=false`, any tenant-binding endpoint returns 503 with the stable code `AUTH_NOT_CONFIGURED`, which is the posture the production overlay inherits until Prompt 7 lands real auth.

The behavioural contract is exercised end-to-end by `scripts/smoke-test.sh`, which asserts (against a locally-running API) the ETag round-trip, idempotency replay-match and replay-mismatch, the `Location` URL is fetchable, the resolution_status state machine rejects forbidden transitions, tenant binding hides cross-tenant resources behind 404, the body size limit returns 413 ProblemDetail, the canonical YAML is reachable at `/v1/openapi.yaml`, the FastAPI auto-generated `/openapi.json` is not exposed, and the `traceparent` response header is present when an OTel exporter is configured.

219 tests pass (151 from before Prompt 6, 4 from Workstream A, plus 64 new from Workstream E covering complaints, batches, health, ProblemDetail handlers, middleware, observability, auth fail-closed, OpenAPI example validation, and the Alembic baseline migration end-to-end against a fresh testcontainer).

One real bug was caught by the new tests and fixed: the `BodySizeLimitMiddleware` was raising `RequestBodyTooLarge`, but exceptions raised inside `BaseHTTPMiddleware.dispatch` do not flow through FastAPI's registered exception handlers. The middleware now materialises the ProblemDetail JSONResponse directly using the exception class's `code`, `status`, `title`, and `type_suffix` so the wire shape matches the handler path.

The fixture seed ordering was also fixed (institutions flushed before complaints so the FK constraint sees them).

## Decisions locked

- ADR 0028 — FastAPI application structure: factory pattern; ProblemDetail via FastAPI exception handlers (not middleware); middleware order body_size_limit → traceparent → correlation_id; OTel owns trace context (custom middleware observes only); structlog binds trace_id + span_id + correlation_id; FastAPI auto-generated openapi/docs/redoc disabled; cursor pagination opaque base64 of `(received_at, complaint_id)`; explicit resolution_status state machine; UUID v7 via `uuid-utils`; `greenlet` runtime dependency for SQLAlchemy async bridge.
- ADR 0029 — Idempotency-Key policy: 24-hour TTL, body-hash on store, 409 on key reuse with different body, `Idempotency-Replayed: true` on cache hit, supported on POST and PATCH.
- ADR 0030 — Health probe semantics: three probes (`/live` no I/O, `/ready` DB ping with 1-second cache, `/startup` alembic_version presence); `SELECT 1` not write-capability; flaps alerted, not auto-remediated.
- Part 2 closed: smoke test is the local-dev gate that demonstrates the behavioural contract holds against a running app.

## Decisions deferred (to a named future prompt / part)

- mTLS termination, HMAC verification, OAuth client_credentials — **Prompt 7**.
- ADR 0027 HMAC contract amendment — **Prompt 7** (lands with the implementing code).
- Rate limiting per institution; idempotency-record sweep job — **Prompt 7**.
- ADR 0029 amendments: concurrent-duplicate-POST policy; replay-header safelist — **Prompt 7**.
- ADR 0028 amendment: refine the "middleware cannot raise SBSAPIException" wording to be project-specific rather than universal — **Prompt 7**.
- 413 path observability: at least an `X-Correlation-Id` echo on early rejection — **Prompt 7**.
- Bounded chunked-read replacement for `await request.body()` slow path; primary cap at reverse proxy — **Prompt 7**.
- Smoke-test configuration-aware fixes (read configured max body size; pin tracing exporter mode) — **Prompt 8**.
- Migration test schema isolation (drop the hand-drop pattern; recreate the schema per test) — **Prompt 8**.
- OpenAPI examples test strict mode (no silent skips) — **Prompt 9** (lands with conformance suite).
- Cursor HMAC signing — **Part 3** hardening.
- `pendiente → pendiente` self-edit policy: drop, restrict to named mutable fields, or land an audit-event hook before Part 3 — **Part 3** (when the audit log requirements are concrete).
- Tier 2 batch upload pipeline; synthetic complaint data generator — **Prompt 8**.
- UI wiring — **Prompt 10**.
- BETO classifier and the embedding storage decision (column vs join table; dimension) — **Prompt 11**.
- Real CI workflow for FastAPI tests — **Prompt 8** (if it fits; otherwise post-sprint).
- Helm chart, Terraform modules, observability stack (Prometheus, Grafana, Loki, OTel collector) — **Part 9**.
- DB ping with write-capability or replication-lag check — **Part 9** (if read replicas are added).
- ProblemDetail extension policy documentation — **Prompt 9**.
- Production ProblemDetail `type` URI namespace under `sbs.gob.pe` — needs SBS sign-off (placeholder retained).

## Decisions flagged for cross-model review

The Prompt 6 spec named six. Cross-review covered all six implicitly and named additional concerns; the disposition is in the Triage section above. Specifically:

- Exception handlers vs middleware for ProblemDetail — cross-review pushed back on the ADR's wording (too broad); fix deferred to Prompt 7.
- Disabling FastAPI's auto-generated openapi — cross-review accepted the trade-off (drift detection lives in the schema-match test pair).
- State transition graph completeness — cross-review did not push back; `second-opinion` flagged the `pendiente → pendiente` self-edit (above) as the audit-gap risk; deferred to Part 3.
- DB-ping 1-second cache window — cross-review accepted it as documented (operator can disable via `SBS_API_READINESS_CACHE_SECONDS`).
- 24-hour idempotency TTL — no pushback.
- AUTH_STUB_ENABLED fail-closed posture — no pushback; cross-review confirmed the env-var seam is correct.

## Subagent verdicts

- `reviewer` — APPROVE WITH NITS (body-size middleware deliberately materialises ProblemDetail directly; documented in ADR 0028 §Consequences. `/health/startup` added beyond the prompt's "triad" wording; consistent with ADR 0030).
- `architect-guard` — APPROVE WITH AMENDMENT (three new ADRs land Accepted in the same commit as the code, per the protocol).
- `doc-sync` — APPROVE (CONTRIBUTING.md references the three scripts; PLAN.md Part 2 marked closed; DECISIONS.md has four new entries; adr/README.md has rows 0028, 0029, 0030; CLAUDE.md has the single pointer to the API run command).
- `regulator-readability` — PASS (no banned phrasing; ProblemDetail strings address the integrator directly with the next-action; ADR tone is calm-engineer-briefing).
- `benchmark-checker` — APPROVE (all three new ADRs cite specific sections of `docs/research/market-comparators.md` and named external comparators with specificity).
- `second-opinion` — WEAKNESS-FLAGGED, does not block (see Adversarial review section above).

## Paste-ready block for the maintainer

> Prompt 6 closed. Part 2 closed. Branch `part-02/fastapi-scaffold-and-ingestion-endpoints` ready for PR. 219 tests pass. Smoke test exercises the behavioural contract against a locally-running API. Three new ADRs (0028, 0029, 0030) land Accepted. Cross-review triage filed in `docs/reviews/2026-05-18-fastapi-scaffold-and-ingestion-endpoints.md`. Adversarial review flagged the `pendiente → pendiente` self-edit audit-gap; tracked for Part 3 (audit log). No blockers. Next prompt: Prompt 7 — mTLS + HMAC + OAuth, idempotency sweep job, rate limiter, and the ADR 0027 HMAC contract amendment.

## Notes

- Greenlet on macOS arm64: the wheel was not auto-installed by `uv sync` of the root pyproject in this session; pinning `greenlet>=3.0.0` in `api/pyproject.toml` and re-syncing the API workspace member resolved it. Now documented in ADR 0028 §11.
- Cross-review needed `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` pointed at the WBG bundle to reach Azure OpenAI through Zscaler. The harness shell did not inherit these from the parent zsh; the `docs/setup/corporate-proxy-and-zscaler.md` recipe is correct as written.
- Testcontainers + Alembic combination required wrapping the migration call in `asyncio.to_thread` because Alembic's `env.py` calls `asyncio.run` which conflicts with pytest-asyncio's outer event loop. The pattern is in `tests/test_alembic_migration.py:_run_alembic_in_thread`.
- The previous Claude Code session timed out mid-stream; this resumption began with a survey of what landed on disk (workstreams A, B, C — package scaffold, docker compose, alembic baseline) and added workstreams E (tests) and F (smoke test) plus the three ADRs and the doc updates. The state was verified at the start by reading every existing file in `api/sbs_api/`, `tests/`, `scripts/`, and `api/migrations/` before writing anything.
