# Cross-model review — fastapi-scaffold-and-ingestion-endpoints

- **Date:** 2026-05-18
- **Model:** gpt-5.4
- **Target:** fastapi-scaffold-and-ingestion-endpoints

---

## Summary

This diff is mostly documentation, tests, and one functional fix in `api/sbs_api/middleware/body_size_limit.py`. The main code change is correct in intent: it avoids relying on FastAPI exception handlers from inside `BaseHTTPMiddleware`, which is a real Starlette/FastAPI edge case and a common source of inconsistent error responses.

I looked for:
- contract drift between ADRs, tests, and code comments
- middleware behavior under failure and observability requirements
- one-command/local-dev claims versus actual scripts and defaults
- places where tests may give false confidence
- regulator-relevant failure modes: silent drift, auth fail-open, trace mismatch, data leakage, non-deterministic health behavior

The strongest concern is not the body-size fix itself. It is that several new tests and ADR statements appear internally inconsistent, which suggests some of this was written faster than it was checked against the running code.

## Disagreements with primary review

1. **The new body-size middleware fix is directionally right, but the ADR overstates the rule.**
   `docs/adr/0028-fastapi-application-structure.md:141-146` says a middleware that needs to raise an `SBSAPIException` cannot do so because FastAPI handlers do not run for exceptions raised inside `BaseHTTPMiddleware.dispatch`. That is true for this chosen middleware style, but written as a blanket rule it is too broad. In Starlette/FastAPI this depends on where the exception is raised in the ASGI stack and which middleware base class is used. The ADR should describe the project-specific constraint, not a universal one.

2. **The startup probe ADR and the migration test contradict each other.**
   `docs/adr/0030-health-probe-semantics.md:100-105` says startup checks for the *presence* of any `alembic_version` row, not the exact head revision.
   But `tests/test_alembic_migration.py:4-5` docstring says “ADR 0030's startup probe asserts `alembic_version` matches a known head”, and `tests/test_alembic_migration.py:99-105` asserts exact revision `20260518_0001`.
   The test for migration correctness is fine. The description is not. This matters because probe semantics are operational policy.

3. **The smoke test is described as authoritative, but it is not stable enough for that claim.**
   `scripts/smoke-test.sh:243-253` accepts `traceparent` being absent depending on exporter settings.
   `docs/CONTRIBUTING.md:86-89` and `docs/PLAN.md:94-95` present the smoke test as the proof that the behavioral contract holds. A test with environment-dependent pass conditions is useful locally, but it is weak as a release gate unless the environment is pinned.

## Risks not flagged elsewhere

1. **413 responses likely lose observability headers by design.**
   `api/sbs_api/middleware/body_size_limit.py:33-35, 60-76` now returns `JSONResponse` directly from the outer middleware.
   `docs/adr/0028-fastapi-application-structure.md:40-49` says middleware order is `body_size_limit → traceparent → correlation_id`.
   `tests/test_middleware.py:131-152` explicitly expects no `X-Correlation-Id` header on 413. By the same logic, `traceparent` will also usually be absent on 413 because inner middleware never runs.
   That conflicts with the stated north-star that observability is first-class. Industry practice in API gateways and service meshes is to preserve a request identifier even for early rejections. Envoy and AWS API Gateway both emit request IDs on rejected requests. Here, early rejection is sensible, but complete loss of correlation on one important abuse path is a gap.

2. **The middleware still reads the full body into memory on the slow path.**
   `api/sbs_api/middleware/body_size_limit.py:68-76` uses `await request.body()` and only then checks `len(body)`.
   This means a client without `Content-Length`, or with a false small `Content-Length`, can still force the process to buffer the whole request before rejecting it. The comment says this guards against a missing or lying `Content-Length`, but it does not cap memory during read. For a regulator-facing API, that is not enough protection against oversized or malicious bodies. Industry practice is incremental read with cut-off at limit, usually at reverse proxy and, if needed, again in app code.

3. **The smoke test hard-codes a default body-size assumption that may drift from configuration.**
   `scripts/smoke-test.sh:217-226` says “256 KiB is the default” and sends 300 KiB.
   `api/sbs_api/middleware/body_size_limit.py` reads `get_settings()`, so the actual limit is configuration-driven. If the default changes, the smoke test becomes misleading. This is a standards-over-invention project; test inputs that depend on config should read the same config source or set the value explicitly.

4. **The idempotency ADR does not address concurrent duplicate requests.**
   `docs/adr/0029-idempotency-policy.md:20-41` defines lookup, hash comparison, and replay behavior, but not the race where two identical POSTs with the same key arrive before either record is committed.
   Without a clear “insert placeholder first under unique constraint, then complete response atomically” rule, duplicate side effects are still possible under concurrency. Stripe’s public guidance and common payment API practice handle this explicitly because it is the hard part of idempotency, not the TTL.

5. **The idempotency ADR stores and replays response headers without defining a safelist.**
   `docs/adr/0029-idempotency-policy.md:21-23, 34-35` says `response_headers` are stored and replayed.
   If implemented literally, this risks replaying headers that should be per-request, hop-by-hop, or time-varying. At minimum, `Date`, `Transfer-Encoding`, `Connection`, and tracing/correlation headers should not come from storage. Stripe-style patterns usually safelist explicit business headers for replay.

6. **The health-readiness cache design is process-global and test-oriented, but carries real multi-worker ambiguity.**
   `docs/adr/0030-health-probe-semantics.md:89-92` says the cache is a module-level variable in `routes/meta.py`.
   This means readiness can differ between workers in a multi-process deployment. That is not always wrong, but it should be named as an operational property, not just a test convenience. With Uvicorn/Gunicorn-style workers, each worker will hold its own cache window and DB failure view.

7. **The migration test uses manual table drops rather than schema isolation.**
   `tests/test_alembic_migration.py:18-28` drops named tables individually.
   This is brittle: adding a table later can leave residue and produce false positives. For Alembic migration tests, a dedicated schema or database recreated per test is more dependable. This is especially relevant because the test claims to validate a “fresh DB”.

8. **The OpenAPI examples validation test is intentionally partial, but the pass condition is weak.**
   `tests/test_openapi_examples_validate.py:56-76` skips unmapped examples silently and only asserts a few core examples were parsed.
   For a platform that treats the OpenAPI file as canonical, this allows new examples to be added unvalidated with no CI failure. That is reasonable during rapid build-out, but it is not enough for a regulator-grade contract unless there is another strict spec example validation step.

9. **`greenlet` added as a runtime dependency needs a reason in code or ADR, not only package metadata.**
   `api/pyproject.toml:9-16` adds `greenlet>=3.0.0`.
   There is no matching note in the ADRs or docs explaining why it is needed. Since the stack is async (`asyncpg`, SQLAlchemy async engine), this will be questioned in review. If it is needed for Alembic or SQLAlchemy internals under current usage, say so. If not, this may be dependency creep.

## Recommended actions

1. **Fix the 413 path so it preserves minimal observability.**
   Keep early rejection, but add at least one correlation mechanism on the response. Two acceptable options:
   - generate/echo `X-Correlation-Id` in `BodySizeLimitMiddleware` before returning 413
   - or move correlation ID outermost and keep body-size enforcement inner, while ensuring body is not read before the limit check
   If you keep the current order, document clearly that 413s intentionally omit trace and correlation headers.

2. **Replace full-body buffering with incremental size enforcement.**
   In `api/sbs_api/middleware/body_size_limit.py:68-76`, stop using `await request.body()` for the guard path. Implement bounded chunked read and stop once `max_bytes + 1` is seen. Better still, enforce request size at the ingress proxy as primary control and keep the app check as secondary. Comparator: NGINX `client_max_body_size`, Envoy `max_request_bytes`.

3. **Tighten the idempotency design for concurrency.**
   Update `docs/adr/0029-idempotency-policy.md` to specify:
   - unique insert or upsert of an in-progress record before handler execution
   - how concurrent same-key requests behave
   - transaction boundaries
   - whether failures are cached and which failures are not
   Without this, the stated guarantee is incomplete.

4. **Define a replay-header safelist.**
   Amend `docs/adr/0029-idempotency-policy.md` to replay only explicit headers such as `Location`, `ETag`, and `Idempotency-Replayed`, not arbitrary stored headers.

5. **Resolve the startup probe inconsistency.**
   Align:
   - `docs/adr/0030-health-probe-semantics.md:100-105`
   - `tests/test_alembic_migration.py:1-5, 99-105`
   The migration test can still assert exact head; just stop claiming the startup probe does.

6. **Make the smoke test configuration-aware.**
   Either:
   - set required env vars inside `scripts/smoke-test.sh`, or
   - query the configured max body size and tracing mode, or
   - explicitly state that the script is for the default local profile only
   Right now the docs present it as more universal than it is.

7. **Strengthen OpenAPI example validation.**
   Change `tests/test_openapi_examples_validate.py:56-76` so new named examples fail unless explicitly mapped or explicitly ignored with a reason. Canonical-contract projects should not silently skip new examples.

8. **Document why `greenlet` is required.**
   Add one short note in `docs/adr/0028-fastapi-application-structure.md` or a dev/setup doc. For auditability, every runtime dependency added to the API service should have a stated purpose.

9. **Improve the migration test isolation.**
   Prefer recreating a fresh database/schema over hand-dropping named tables in `tests/test_alembic_migration.py:18-28`. This reduces future maintenance errors as the schema grows.

## Triage

**Disagreements with primary review**

1. *ADR 0028 overstates the middleware-handler rule.* **accept (defer wording fix to Prompt 7).** The Starlette/FastAPI exception-handler behavior depends on middleware base class. The ADR's current text is correct for `BaseHTTPMiddleware` (what this project uses) but should not read as universal. Tracked for the Prompt 7 ADR amendment pass.
2. *Startup probe ADR vs migration test wording.* **accept (fixed in this prompt).** Updated `tests/test_alembic_migration.py` docstring to align with ADR 0030's "presence not exact head" policy. The test's exact-head assertion is the *stronger* property; the runtime probe stays at presence.
3. *Smoke test pass conditions are environment-dependent.* **accept (defer pinning to Prompt 8).** The smoke test is documented as the local-dev gate in `docs/CONTRIBUTING.md`; pinning it as a CI release gate is a Prompt 8 task when the GitHub Actions matrix lands.

**Risks not flagged elsewhere**

1. *413 loses observability headers by design.* **defer to Prompt 7.** The current behavior is documented in ADR 0028 (Consequences). Adding `X-Correlation-Id` to the 413 response is a small refinement; the wider question of "what does the smoke test assert on early rejections" belongs alongside the rate-limiter work in Prompt 7.
2. *Full-body buffering on the slow path.* **defer to Prompt 7.** Reverse-proxy enforcement (NGINX `client_max_body_size`) is the primary control in production; the app check is secondary. Chunked-read implementation is non-trivial under Starlette's `BaseHTTPMiddleware` and is a Prompt 7 hardening item alongside other abuse-path defenses.
3. *Smoke test hard-codes 256 KiB.* **defer to Prompt 8.** Test should read `SBS_API_MAX_REQUEST_BODY_BYTES` from the running config. Same Prompt 8 batch as the pin-the-environment fix above.
4. *Idempotency under concurrent identical POSTs.* **defer to Prompt 7.** ADR 0029 covers the steady-state policy; the concurrency-correctness amendment (placeholder-insert-under-unique-constraint) lands alongside the sweep job and rate limiter in Prompt 7.
5. *Replay-header safelist.* **defer to Prompt 7.** Same Prompt 7 batch. Current implementation stores the small allowlist the route handlers compute (`Location`, `ETag`, `Idempotency-Replayed`), but the ADR does not document this constraint. Amend ADR 0029 to explicit safelist.
6. *Readiness cache is process-global → per-worker view in multi-worker deploys.* **accept as documented property.** This is the correct trade-off for the May 25 sandbox (one worker per pod, multi-pod, load balancer aggregates). The Helm chart in Part 9 will document the deployment posture. No ADR change needed.
7. *Migration test uses hand-drop rather than schema isolation.* **defer to Prompt 8.** Acceptable for the May 25 sandbox; schema-per-test is cleaner but adds testcontainer startup time. Re-evaluate when the CI matrix lands in Prompt 8.
8. *OpenAPI examples test skips unmapped examples silently.* **accept (defer strict mode to Prompt 9).** The test is intentionally permissive during rapid build-out (Prompt 6); the strict-mode flip lands with the conformance suite in Prompt 9.
9. *`greenlet` runtime dep needs a stated reason.* **accept (fixed in this prompt).** Added §11 to ADR 0028 explaining the SQLAlchemy async bridge.

**Net disposition.** Two fixes applied in this prompt (startup probe wording, greenlet documentation). All other findings tracked for Prompt 7 (concurrency, replay safelist, 413 observability, full-body buffering) and Prompt 8/9 (smoke-test pinning, schema isolation, strict examples).
