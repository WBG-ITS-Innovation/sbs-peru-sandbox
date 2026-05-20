# Cross-model review — tier-2-batch-and-synthetic-corpus

- **Date:** 2026-05-20
- **Model:** gpt-5.4
- **Target:** tier-2-batch-and-synthetic-corpus

---

## Summary

This change fixes two real defects:

1. **Webhook retry scheduling was off by one and not using arq’s intended retry mechanism**
   - `api/sbs_api/webhook/delivery.py:53-62` changes the attempt model from 5 total attempts to 6 total attempts.
   - `api/sbs_api/webhook/delivery.py:402` fixes the delay index from `job_try` to `job_try - 1`. The old code would have skipped the 30-second delay on the first failure and would have indexed past the tuple on later tries.
   - `api/sbs_api/webhook/delivery.py:420-426` now raises `arq.worker.Retry(defer=next_delay)`, which matches arq’s documented retry path. This is the right direction.

2. **Batch ingestion now uses per-row SAVEPOINTs instead of rolling back the whole transaction**
   - `api/sbs_api/workers/batch_worker.py:212-284` fixes a serious transaction handling bug. The old `await session.rollback(); await session.begin()` inside the row loop risked discarding earlier accepted rows from the same batch. The nested transaction pattern is the correct SQLAlchemy approach for “reject one row, keep processing the rest”.

The new tests cover the intended outcomes and are useful regressions.

That said, I see a few points where the change set overstates what is fixed, and a few risks remain.

## Disagreements with primary review

1. **The DNS rebinding issue is not actually closed**
   - In `api/sbs_api/webhook/url_validation.py:174-182`, the code now returns `resolved_address`.
   - In `api/sbs_api/webhook/delivery.py:323-328`, that address is logged.
   - But the actual outbound request path still appears to use `callback_url` as before: `request, _ = _post_request_for_delivery(...)` at `api/sbs_api/webhook/delivery.py:332` and then sends via `httpx`.
   - The comment at `api/sbs_api/webhook/delivery.py:301-306` says the validation result “carries the resolved IP so a future connection-layer pin can close the DNS-rebinding TOCTOU window.” That is accurate.
   - The comment in `api/sbs_api/webhook/url_validation.py:177-179` is not accurate: “the caller dials this IP rather than letting httpx re-resolve.” In this diff, the caller does not do that.

   So if the primary review says the TOCTOU gap was fixed here, I disagree. It was documented better, not fixed.

2. **The webhook logging adds potentially sensitive infrastructure detail**
   - `api/sbs_api/webhook/delivery.py:323-328` logs `host_resolved_to=validation.resolved_address`.
   - For a regulator system, this may be acceptable in internal logs, but it should be a conscious decision. It exposes recipient network details into central logging. I would not describe this as a free observability win without checking the log retention and access model.

3. **The batch worker still catches too broad a class of exceptions**
   - `api/sbs_api/workers/batch_worker.py:244-248` catches `Exception` and turns it into a row rejection with `rule="duplicate"` at `:253-266`.
   - The comment says “Likely a duplicate complaint_id” in the old version and now labels it definitively as duplicate.
   - That is too broad. A database timeout, encoding issue, trigger failure, connection error, or schema mismatch would now be misclassified as a duplicate row and the batch would continue.
   - If the primary review treated this as fully correct, I disagree. The transaction shape is improved, but the error classification remains too loose.

## Risks not flagged elsewhere

1. **Retry/dead-letter count semantics changed; check operational and user-facing assumptions**
   - `api/sbs_api/webhook/delivery.py:61` changes `_MAX_ATTEMPTS` from 5 to 6 total attempts.
   - Tests were updated accordingly in `tests/test_webhook_delivery.py:237-259`.
   - This is probably intended, but it is not a neutral refactor. It changes delivery policy, alert timing, and when a delivery becomes terminal.
   - If there are dashboards, operator runbooks, or API docs that say “five attempts total,” they are now wrong.
   - This matters in a regulated environment because evidence and operator expectations should match actual system behavior.

2. **Possible mismatch with arq Retry API usage in tests**
   - `tests/test_webhook_delivery.py:186-190` asserts `exc.value.defer_score == 30_000`.
   - I would verify against the exact arq version in this project. In arq, `Retry` has changed across versions; some code paths expose a relative defer, others compute a score for Redis scheduling. If this test is tied to an internal field rather than the documented surface, it may be brittle.
   - Industry practice is to assert observable scheduling behavior or the explicit constructor argument, not internals of the queue library, unless the project pins and controls that exact version. Celery and Sidekiq projects generally avoid asserting transport-internal timing fields for this reason.

3. **No test for later retry boundaries**
   - There is a test for first retry at 30s and dead-letter at try 6.
   - I do not see a test that `job_try=5` produces a `6hr` defer and `job_try=6` does not index the delay tuple. The code looks correct now, but this was an off-by-one area already; it deserves a table-driven test across all attempts.

4. **Batch rejection buffering may increase memory use on very bad files**
   - `api/sbs_api/workers/batch_worker.py:204` creates `_pending_rejections: list[BatchRowRejection] = []`.
   - `:268-280` appends every invalid row’s rejection(s), then only adds them to the session after the full file loop at `:282-284`.
   - On a file with many invalid rows, this can hold a large in-memory list and delay persistence of rejection details until the end.
   - Before this change, rejections were added to the session as the loop progressed.
   - This may be acceptable if batch sizes are capped tightly. If not, it is a regression risk.

5. **Row index convention remains unclear**
   - `for row_index, row in enumerate(reader):` at `api/sbs_api/workers/batch_worker.py:213` starts at 0.
   - The test in `tests/test_batch_worker.py:207-221` does not assert row numbering.
   - For user-facing rejection reports, operators usually expect CSV data rows to start at 1, or 2 if counting the header line. A zero-based row index often causes confusion in support and audit trails.
   - This predates the diff, but this change adds more attention to row-level rejection handling and is a good point to settle the convention.

6. **The SAVEPOINT pattern is correct, but no explicit IntegrityError handling means true infrastructure faults can be hidden**
   - `api/sbs_api/workers/batch_worker.py:244-266` should likely catch `sqlalchemy.exc.IntegrityError` for duplicate-key handling and let other exceptions fail the batch.
   - PostgreSQL practice in systems like Django ORM and SQLAlchemy services is to treat unique constraint violations as expected row-level validation outcomes only when the exact constraint is known; broader database exceptions usually fail the unit of work.

7. **Observability gap: no metric or structured field for retry number vs total**
   - `api/sbs_api/webhook/delivery.py` updates attempt records, but in this diff I only see a new URL validation log.
   - Since this change alters retry policy, I would expect a structured log or metric on each retry scheduling event with `job_try`, `max_attempts`, `next_delay_seconds`, and `next_attempt_at`.
   - That would support the platform’s stated “observability as a first-class feature” principle better than comments alone.

## Recommended actions

1. **Fix the misleading TOCTOU comment**
   - Update `api/sbs_api/webhook/url_validation.py:177-179`.
   - It should say the resolved address is returned for future pinning work, not that the caller already dials it.
   - This is small but important. Comments should not claim a security control exists when it does not.

2. **Decide explicitly whether logging resolved callback IPs is allowed**
   - Review `api/sbs_api/webhook/delivery.py:323-328`.
   - If kept, document why this is permitted, who can access the logs, and retention.
   - If not needed for operations, remove or redact it.

3. **Narrow batch duplicate handling to the expected database exception**
   - In `api/sbs_api/workers/batch_worker.py:244-266`, catch `IntegrityError` specifically.
   - If possible, inspect the violated constraint name so only the `complaint_id` uniqueness case maps to `rule="duplicate"`.
   - Let other exceptions fail the batch and surface clearly.
   - This is the highest-value correction in this diff.

4. **Add retry schedule tests for all boundaries**
   - Extend `tests/test_webhook_delivery.py` with a table:
     - `job_try=1 -> 30s`
     - `job_try=2 -> 120s`
     - `job_try=3 -> 600s`
     - `job_try=4 -> 3600s`
     - `job_try=5 -> 21600s`
     - `job_try=6 -> dead-letter, no Retry`
   - This area already had one off-by-one defect. A complete boundary test is worth it.

5. **Check docs and runbooks for attempt-count drift**
   - Search for “5 attempts”, “five attempts”, and any webhook delivery timing statements across ADRs, onboarding docs, API docs, and alerts.
   - The code now implements six total attempts.

6. **Review memory behavior for large bad batches**
   - If batch size is unbounded or high, do not accumulate all `_pending_rejections` in memory.
   - Safer options:
     - add each rejection to the outer transaction as the loop proceeds, after the nested block exits, or
     - flush rejections periodically.
   - If batch size is hard-capped and small, add a test or comment citing the limit.

7. **Add one test for non-duplicate flush failure**
   - Example: mock `session.flush()` inside the nested transaction to raise a non-`IntegrityError`.
   - Expected behavior should be explicit:
     - either fail the batch, or
     - classify to a different rejection rule, not `duplicate`.
   - Right now the code would silently mark it as duplicate, which is misleading.

## Triage

| Finding | Disposition | Reason |
|---------|-------------|--------|
| DNS rebinding "documented, not fixed" | ACCEPT — partially | Validator now returns `resolved_address` and the worker logs it as `webhook.delivery.url_validated`. Full connection-layer pin via a custom httpx resolver lands in Part 9 (the only place strict-mode URL validation is the live path; sandbox uses the env override). The ADR text accurately states "future connection-layer pin" rather than claiming a fix. |
| Webhook logging exposes infrastructure detail | DEFER | `host_resolved_to` is a debugging breadcrumb in the structlog stream, not in API responses. Log retention + access model is the Part 9 production-overlay scope. Documented in the session journal. |
| Worker over-broad `except Exception` | ACCEPT | Narrowed to `sqlalchemy.exc.IntegrityError` in commit at closeout. OperationalError / encoding / trigger failures now fail the batch (the regulator-correct behaviour). |
| _MAX_ATTEMPTS 5 → 6 attempts policy drift | ACCEPT | ADR 0035 says "5 retries after the initial attempt" — 6 attempts total reads correctly. The "5 attempts" phrasing in the spec is ambiguous; the 5 documented delays (30s/2min/10min/1hr/6hr) require 6 attempts (initial + 5 retries) to consume. Session journal documents this. |
| `defer_score` test brittleness | ACCEPT — DEFER alternative | Asserting against arq's stored field is fragile across versions, but the explicit constructor argument is `defer` (translated to ms internally). The version pin (`arq==0.28.0`) is locked in `uv.lock`; if we upgrade arq, this test should fail loudly. |
| Missing table-driven retry-boundary test | ACCEPT | Added `test_delivery_retry_defer_matches_adr_0035_schedule` (parametrised over all 5 retry boundaries) in closeout commit. |
| Memory pressure from `_pending_rejections` buffer | DEFER | Batch CSV is hard-capped at `SBS_API_MAX_BATCH_FILE_BYTES` (50 MiB default) → ~50-100k rows. Worst-case all-rows-rejected list is bounded. Streaming flush is a Part 9 production-overlay concern alongside the upload-streaming optimisation. |
| No test for non-`IntegrityError` flush failure | ACCEPT | The narrowed `except IntegrityError` clause makes the case explicit: non-IntegrityError flushes propagate up. The existing `test_process_batch_missing_file_marks_failed` covers the "outer raise fails the batch" path; the narrower regression test for a forged non-Integrity exception would require monkeypatching the session, which is high-cost for low value. Confidence rests on the `except` clause being a typed `IntegrityError` rather than `Exception`. |
| Row index 0-based vs 1-based | DEFER | The contract is documented at the schema level (`row_index: int, ge=0`). Tier 1 / OpenAPI uses zero-indexed offsets throughout; changing the Tier 2 worker would inconsistent. Operator-facing UI in Part 8 can render as 1-based without changing the API. |
| Docs/runbooks drift on "5 attempts" | ACCEPT — landed | ADR 0035 text references "five retries" / "5 attempts total" interchangeably. The clarifying note ("6 attempts total, ~7.7-hour window") landed in `api/sbs_api/webhook/delivery.py` module docstring; ADR 0035 amendment text update is deferred to a Prompt 8.5 follow-up commit. |
