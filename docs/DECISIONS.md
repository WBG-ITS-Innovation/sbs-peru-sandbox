# Decisions Log

One line per non-trivial decision. Date | decision | rationale.

## Format

YYYY-MM-DD | [PartN] decision summary | one-line rationale.

## Entries

2026-05-16 | [Part1] Retired `scripts/requirements-harness.txt`; harness deps live in root `pyproject.toml` `dev` group; install via `uv sync` | uv project initialization (Prompt 3). See ADR 0021.
2026-05-17 | [Part1] Locked May 25 sprint kickoff scope: Parts 2/3/4 full, Parts 5/6/7/8/11 reduced, Parts 9/10 deferred entirely; PLAN.md restructured with per-Part May 25 scope subsections | May 25 sprint kickoff scope-lock (Prompt 4). See ADR 0025.
2026-05-18 | [Part2] Anexo 1-A May 25 sandbox uses a curated 15-field subset reconciled against Resolución SBS N° 04036-2022; full code lists + PII fields deferred to Part 11 | Prompt 5. See ADR 0026.
2026-05-18 | [Part2] OpenAPI 3.1 specification at api/openapi/sbs-api-v1.yaml is the canonical contract; Pydantic v2 models implement it; JSON Schemas exported; match-test enforces alignment | Prompt 5. See ADR 0027.
2026-05-18 | [Part2] RFC 9457 problem+json is the SBS error envelope; placeholder `type` namespace pending SBS sign-off; error catalog committed at api/openapi/error-catalog.md | Prompt 5. Tracked in docs/sessions/2026-05-18-prompt-05-open-questions.md.
2026-05-18 | [Part2] Developer portal uses Stoplight Elements (CDN) with Redoc 2.x as documented fallback; vendoring deferred to Part 7 / Prompt 9 | Prompt 5. See docs/research/2026-05-18-prompt-05-stack-validation.md §E.
2026-05-18 | [Part2] FastAPI application structure locked: factory pattern, ProblemDetail via FastAPI exception handlers (not middleware), middleware order body_size_limit → traceparent → correlation_id, OTel owns trace context, FastAPI auto-generated openapi/docs/redoc disabled, cursor pagination opaque base64 of `(received_at, complaint_id)`, explicit resolution_status state machine, UUID v7 via uuid-utils | Prompt 6. See ADR 0028.
2026-05-18 | [Part2] Idempotency-Key policy locked: 24-hour TTL, body-hash on store, 409 on reuse with different body, `Idempotency-Replayed: true` on cache hit, supported on POST and PATCH | Prompt 6. See ADR 0029.
2026-05-18 | [Part2] Health probe semantics locked: three probes (live, ready, startup) matching Kubernetes model; ready has 1s DB-ping cache; startup checks alembic_version presence (not exact head) | Prompt 6. See ADR 0030.
2026-05-18 | [Part2] Part 2 closed: FastAPI scaffold serves the canonical OpenAPI contract; smoke test asserts behavioral contract (ETag round-trip, idempotency replay, tenant binding, state machine, ProblemDetail, body size limit) against the running app | Prompt 6.
2026-05-19 | [Part3] mTLS client authentication contract locked: CN-as-identifier; chain + expiry + revocation validation; `direct` (sandbox) and `proxy` (production) operating modes; `MtlsSubject` carries cert thumbprint into the OAuth cert-binding check | Prompt 7 A0. See ADR 0031.
2026-05-19 | [Part3] OAuth 2.0 client_credentials contract locked: four scopes (`complaints:write/read`, `batch:upload`, `status:read`); 15-minute JWT TTL; cert-bound via RFC 8705 `cnf.x5t#S256`; no refresh tokens, no introspection in sandbox | Prompt 7 A0. See ADR 0032.
2026-05-19 | [Part3] Per-institution rate limiting contract locked: Redis token bucket, two tiers (`large` 1000/min, `small` 100/min) with per-institution override; four `X-RateLimit-*` headers on every authenticated response; 429 ProblemDetail | Prompt 7 A0. See ADR 0033.
2026-05-19 | [Part3] ADR 0027 amended: full HMAC canonical request contract (method/target/timestamp/body-hash/institution_id), `hmac-sha256-v1` algorithm prefix, 5-minute clock skew, 24-hour replay window, per-institution secret with rotation grace | Prompt 7 A0. See ADR 0027 §Amendments.
2026-05-19 | [Part3] ADR 0028 amended ×4: middleware ordering reversed for 413 path so traceparent/correlation_id bind before body-size check; bounded chunked-read on slow path; §Consequences wording narrowed to FastAPI `BaseHTTPMiddleware`; cursor pagination HMAC-signed (closes issue #L) | Prompt 7 A0. See ADR 0028 §Amendments.
2026-05-19 | [Part3] ADR 0029 amended ×2: concurrent-duplicate-POST policy uses placeholder-INSERT under unique constraint with 50ms×3 retry; replay-header safelist enumerated explicitly (Date/Server/trace recomputed, ETag/Location/Content-Type replayed) | Prompt 7 A0. See ADR 0029 §Amendments.
2026-05-19 | [Part3] ADR 0003 (api-authentication) marked Superseded by ADRs 0031/0032/0033 + the 0027 HMAC amendment — Proposed-only ADR replaced before any code referenced it; the three concerns split into separate ADRs for cleaner review surfaces | Prompt 7 A0. See ADR 0003 row in docs/adr/README.md.
2026-05-19 | [Part3] Comparator file §5.A.M added: regulator-domain precedent for the mTLS + OAuth + HMAC + rate-limiting chain (Open Banking UK, RFC 8705, AWS SigV4 §Task 1, Stripe rate-limits) | Prompt 7 A0. See docs/research/market-comparators.md §5.A.M.
