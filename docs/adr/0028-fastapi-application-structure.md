# ADR 0028 — FastAPI application structure

- **Status:** Accepted
- **Date:** 2026-05-18
- **Target prompt / Part:** Prompt 6 / Part 2
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

Prompt 6 lands the runtime that responds to HTTP requests against the
canonical OpenAPI contract from ADR 0027. The package layout, the choice
of where ProblemDetail formatting lives, the middleware ordering, the
ownership of W3C trace context, and a handful of cross-cutting rules all
need a single decision document so the next person who lands a route does
not relitigate them on every PR. Several of these choices have widely-held
defaults in the FastAPI community that this project deliberately departs
from; the divergence and its rationale need to be visible.

## Decision

1. **Application-factory pattern.** `api/sbs_api/app.py::create_app()`
   returns a configured ASGI app. Per-test fresh apps with overridden
   dependencies are the deciding requirement; module-level singletons
   would force a process restart between tests.

2. **ProblemDetail formatting via FastAPI exception handlers, not
   middleware.** A single registered handler renders every
   `SBSAPIException` subclass as RFC 9457 `application/problem+json` with
   the stable `code`, the `type` URI from the configurable namespace, and
   `trace_id` extracted from the OTel-managed current span. Two more
   handlers cover `RequestValidationError` (maps to 422 ProblemDetail with
   field-level errors) and the catch-all `Exception` (body-less 500 — no
   internal information leak, `trace_id` is the support-handoff key).
   Exception handlers compose with FastAPI's own dispatch chain and do
   not need to wrap `BaseHTTPMiddleware.__call__` to catch downstream
   exceptions.

3. **Middleware ordering, outermost to innermost:**
   `body_size_limit` → `traceparent` → `correlation_id`. Body size limit
   must reject before any other processing so a 300 KiB attack does not
   incur trace context, correlation_id binding, or request-body parsing.
   `traceparent` observation precedes `correlation_id` binding so the
   correlation_id logger emits log lines that already carry the OTel
   trace context.

4. **OpenTelemetry owns trace context.** The custom `traceparent`
   middleware observes the OTel-managed context and echoes it on the
   response. It does not parse, repair, or generate independently.
   Malformed inbound `traceparent` is logged at WARN and dropped; OTel's
   FastAPI instrumentation falls through to a fresh span. This avoids the
   dual-context bug where a ProblemDetail's `trace_id` disagrees with the
   exporter's span `trace_id`.

5. **structlog binds `trace_id`, `span_id`, AND `correlation_id`** on
   every log line. The OTel trace_id is the Grafana-to-logs key; the
   correlation_id is the operations-team-to-logs key when the trace
   context was dropped upstream. Binding both makes both keys searchable.

6. **FastAPI's auto-generated `/openapi.json`, `/docs`, `/redoc` are
   disabled.** `FastAPI(openapi_url=None, docs_url=None, redoc_url=None)`
   on construction. The canonical YAML is served at `/v1/openapi.yaml` by
   a dedicated route. Prevents silent drift from the canonical artifact
   that ADR 0027 protects.

7. **Cursor pagination format:** opaque base64-encoded JSON of
   `{"received_at": "<RFC3339>", "complaint_id": "<uuid>"}`.
   Server-decoded, server-validated; tampered cursors return 400 with
   stable code `CURSOR_INVALID`. The cursor is documented in the
   `GET /v1/complaints` description as opaque; clients pass it back
   verbatim.

8. **Configuration via Pydantic Settings.** `api/sbs_api/config.py`
   declares every knob. No `os.environ` reads outside this module. The
   `lru_cache(maxsize=1)` `get_settings()` is the only seam tests need to
   monkey-patch.

9. **Resolution_status state transition graph (explicit):**
   `pendiente → atendido`, `pendiente → anulado`, `pendiente → pendiente`.
   `atendido` and `anulado` are terminal. All other transitions return
   422 with `RESOLUTION_STATUS_TRANSITION_FORBIDDEN`. The
   reason-required-on-terminal rule from Prompt 5's adversarial review is
   retained. The state machine is decoupled from the route handler so it
   can be unit-tested without spinning up the app and re-used by the
   audit log and the approval-queue path in Part 6.

10. **UUID v7 via `uuid-utils`.** The stdlib `uuid` module in Python 3.12
    does not implement v7. `uuid-utils` is the smallest dependency that
    does, pinned in `api/pyproject.toml`. UUID v7 is the time-orderable
    identifier the spec carries for `batch_id` and internal records.

11. **`greenlet` as a runtime dependency.** SQLAlchemy's async engine
    bridges sync-style ORM operations onto the asyncio event loop via
    `greenlet`. The dependency is implicit in SQLAlchemy 2.x async, but
    on macOS arm64 the wheel is sometimes not auto-installed; pinning
    `greenlet>=3.0.0` in `api/pyproject.toml` makes the requirement
    explicit and reproducible.

## Precedent

The factory pattern, dependency-injection mode, and exception-handler
mechanism are documented in the FastAPI core documentation as the project's
recommended pattern. The full-stack-FastAPI-template from Tiangolo is the
reference implementation reviewers will recognise.

The state-machine choice has a regulator-domain precedent in the CFPB
Consumer Complaint Database — see
[docs/research/market-comparators.md §2.1](../research/market-comparators.md#21-us-cfpb-consumer-complaint-database).
CFPB's complaint lifecycle uses an analogous *received → in-progress → closed*
transition graph with explicit forbidden walkbacks; the SBS sandbox's
`pendiente → atendido / anulado` mirrors that shape with Resolución
SBS N° 04036-2022 vocabulary.

The W3C Trace Context specification (W3C-TR/trace-context/) is the
authority on `traceparent` parsing; OTel's FastAPI instrumentation library
implements it. Owning trace context once, in OTel, is the documented
OTel-SDK pattern for Python services.

## Divergence

1. **From "the ProblemDetail middleware pattern."** A widely-used recipe
   wraps the ASGI app in a middleware that catches every exception and
   formats ProblemDetail. We diverge because that pattern requires
   re-implementing FastAPI's `RequestValidationError` handling and
   bypasses the dependency-injection error pathway. Exception handlers
   compose with FastAPI's dispatch chain; middleware does not.

2. **From "let FastAPI generate /openapi.json."** The conventional FastAPI
   posture is "the auto-generated OpenAPI is a development aid alongside
   the curated docs." We diverge because ADR 0027 locks the curated YAML
   as the only source of truth; a second source defeats the contract-
   stability property the regulator audience requires.

3. **From "let OTel and the route both stamp the traceparent."** A subtle
   default of FastAPI services with custom tracing middleware is that the
   route handler can stamp its own trace_id (e.g., from a request
   correlation id) which then disagrees with the OTel span. We diverge by
   making OTel the only owner; the ProblemDetail's `trace_id` is read
   back from the OTel current span.

## Consequences

- Tests can rebuild the app per test with `create_app(settings=override)`
  and `app.dependency_overrides[get_auth_context] = ...`. The
  test-container fixture pattern exercised in
  `tests/test_complaints_endpoints.py` relies on this.
- A middleware that needs to raise an `SBSAPIException` cannot — FastAPI's
  exception handlers do not run for exceptions raised inside
  `BaseHTTPMiddleware.dispatch`. The body-size-limit middleware therefore
  materialises a `JSONResponse` with the ProblemDetail body directly. The
  exception class is still used as the source of `code`, `status`, `title`,
  and `type_suffix` so the wire shape matches the handler path.
- Tracing test isolation: tests that need an active span must install a
  real `TracerProvider`. With `OTEL_TRACES_EXPORTER=none` the global
  provider is a no-op and `traceparent` echo is absent — which is the
  documented fallthrough, not a bug.
- The state machine module is the single home for transition logic. New
  states (a hypothetical `en_revisión`) land as a one-line change to
  `ALLOWED_TRANSITIONS` plus a migration of stored data; the rest of the
  code does not need to learn about new states.
- UUID v7 + `uuid-utils` is a small dependency surface (~50 KiB wheel,
  pure Rust) and is acceptable. If stdlib `uuid` adds v7 (Python 3.14
  draft), this ADR is superseded by a removal of the dependency.

## Amendments

### 2026-05-19 — middleware ordering on the 413 path (Prompt 7)

The original §3 declared the order *outermost-to-innermost*
`body_size_limit → traceparent → correlation_id`. Prompt 6 carry-forward
observed that the 413 response is materialised by
`BodySizeLimitMiddleware` *before* `traceparent` and `correlation_id`
bind their context, so the 413 ProblemDetail goes out without a
`traceparent` or `X-Correlation-Id` header. Support handoff on a 413 is
then blind.

**Amendment.** The order is reversed for the 413 path. Outermost-to-
innermost is now `traceparent → correlation_id → body_size_limit`. The
body-size middleware reads `request.state.correlation_id` (set by the
surrounding `CorrelationIdMiddleware`) and includes it in the 413
ProblemDetail. The `traceparent` header is echoed onto the 413 response
by the surrounding `TraceparentMiddleware` on the response path.

The trade-off: a 300 KiB attack now incurs the cost of `traceparent`
parsing and a correlation_id allocation before being rejected. The
mitigation is that a reverse proxy in production caps body size at a
lower threshold than the application, so the application path is only
reached by reasonably-shaped requests.

### 2026-05-19 — bounded chunked-read on the slow path (Prompt 7)

The original §3 noted the slow path reads
`body = await request.body()` and then checks the length. This buffers
the full body before any size check, which means a client that lies
about `Content-Length` can still force a `max_body_size`-bytes
allocation.

**Amendment.** Replace `await request.body()` with a bounded streaming
read: iterate `request.stream()`, accumulate into a `bytearray`, and
abort with `RequestBodyTooLarge` as soon as the running total exceeds
`max_body_size`. The accumulator is then installed on
`request._receive` so the downstream handler reads the same body
without a second network round-trip. Full-body buffering remains
acceptable on endpoints without body-size concerns (auth, health,
openapi).

Production posture: a reverse proxy still applies the primary cap; the
application cap is defense-in-depth.

### 2026-05-19 — narrowed §Consequences wording on middleware constraint (Prompt 7)

The original §Consequences said *"a middleware that needs to raise an
SBSAPIException cannot — FastAPI's exception handlers do not run for
exceptions raised inside `BaseHTTPMiddleware.dispatch`."* The sentence
was too broad: only the `BaseHTTPMiddleware` ABC has this constraint;
pure-ASGI middleware does not.

**Amendment.** The sentence is rewritten as:

> Middleware implemented as FastAPI `BaseHTTPMiddleware.dispatch` cannot
> raise `SBSAPIException` and rely on FastAPI exception handlers to
> materialise the ProblemDetail response, because `BaseHTTPMiddleware`
> sits outside the exception-handler middleware in the dispatch chain.
> Such middleware must materialise the ProblemDetail `JSONResponse`
> directly using the `SBSAPIException` class's `code`, `status`,
> `title`, `type_suffix` fields (see
> `api/sbs_api/middleware/body_size_limit.py` for the pattern).
>
> Pure-ASGI middleware (e.g., starlette's `Middleware` class with a
> `__call__(scope, receive, send)` signature) is *not* subject to this
> constraint and may raise `SBSAPIException` directly. Convert
> middleware to ASGI when exception-handler integration is required.

### 2026-05-19 — cursor signing (Prompt 7, open issue #L)

The original §7 declared cursor format as opaque
base64-encoded JSON. Adversarial review on Prompt 6 surfaced that the
encoding is unsigned: a client that decodes the cursor can mutate the
embedded `received_at` or `complaint_id` and submit it. The server
re-validates the cursor contents against the query, which catches
*most* tampering, but the design contract (cursor is server-controlled,
client passes verbatim) is undermined.

**Amendment.** The cursor is HMAC-signed with a server-side master key.
Encoded as
`base64url(payload || hmac_sha256(key=master_key, msg=payload))` where
`payload` is the JSON object from §7 serialised with sorted keys and
compact separators (so the same logical payload produces the same
cursor regardless of dict ordering). On decode the server splits the
trailing 32 bytes as the signature, recomputes against the payload
with `hmac.compare_digest` (constant-time), and returns 400
`CURSOR_INVALID` on mismatch. The master key is generated at first
boot via `secrets.token_bytes(32)` and persisted at
`dev-ca/cursor-signing-key.bin` (chmod 600) for the sandbox;
production loads from the secret manager.

**Precedent.** AWS SigV4 §Task 1 (CreateCanonicalRequest), cited at
[docs/research/market-comparators.md §5.A.M](../research/market-comparators.md#5am-authentication-signing-and-rate-limiting-for-regulator-facing-apis).
The construction is the same HMAC-over-payload-with-server-key pattern
SigV4 uses for request signing, applied here to opaque pagination
cursors. The constant-time-comparison requirement carries over
verbatim. SBS divergence: the cursor signature is bound to a fixed
master key rather than rotated per-request (rotation is unnecessary
when the cursor payload is short-lived and the master key is held
server-side).
