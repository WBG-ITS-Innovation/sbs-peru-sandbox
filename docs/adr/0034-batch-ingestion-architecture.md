# ADR 0034 — Batch ingestion architecture and worker model

- **Status:** Accepted
- **Date:** 2026-05-20
- **Target prompt / Part:** Prompt 8 / Part 4
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

The institutional integration profile spans two tiers per ADR 0025 and
the Peru sprint survey data. Large banks run Tier 1 near-real-time
ingestion against the per-request API landed in Part 3. Small COOPACs
and financieras submit Tier 2 batches because their core systems
cannot expose a near-real-time API; they export a CSV from the core
once a day or once a week and upload it.

Part 4 lands the Tier 2 batch path. The decisions that need to be
recorded are:

- Sync vs async processing of the uploaded file.
- Which worker runtime carries the asynchronous job.
- Where the CSV is stored between upload and processing.
- How per-row validation relates to the Tier 1 validation pipeline.
- How concurrent batches from the same institution are sequenced.

A regulator-grade system cannot accept an upload, return 200 OK, and
silently lose the work if the process restarts. Async processing must
be durable. The job must survive a uvicorn or worker restart and the
institution must be able to find out what happened to their batch.

## Decision

Tier 2 batch ingestion uses an asynchronous worker pattern.

**Upload.** `POST /v1/batches` accepts a signed multipart upload
(manifest JSON + CSV file) over the Part 3 auth chain (mTLS + HMAC +
OAuth scope `batch:upload`). The endpoint validates the manifest,
streams the CSV to local-filesystem storage at
`data/batches/<batch_id>.csv`, enqueues a `process_batch` job, and
returns 202 Accepted with a `batch_id` and a `Location` header
pointing at the status endpoint.

**Worker runtime: arq.** A separate `worker` process in
`docker-compose.yaml` runs arq against Redis. arq is the chosen
runtime because:

- FastAPI BackgroundTasks runs in the request event loop and offers
  no durability — a uvicorn restart loses the in-flight batch. A
  regulator system cannot lose institutional submissions on a
  restart.
- APScheduler (already in production for the idempotency sweep) is
  cron-shaped (run-every-N-minutes), not queue-shaped (pick up jobs
  as they arrive). Using it for batch dispatch would mean abusing its
  trigger system.
- Celery and RQ are mature alternatives but heavier; arq is
  purpose-built for asyncio Python (matches the stack) and uses
  Redis (already a dependency for HMAC replay and rate limiting). No
  new infrastructure to operate.

**Storage.** Sandbox: local filesystem at `data/batches/<batch_id>.csv`
(gitignored). Production overlay: Azure Blob with lifecycle policies,
deferred to Part 9. The local-filesystem prune job (APScheduler,
7-day retention) is the dev-grade equivalent of object-store
lifecycle.

**Validation pipeline reuse.** The worker validates each CSV row
against the *exact same* Pydantic models as the Tier 1 POST endpoint
(`api/sbs_api/models/anexo_1a.py`). No parallel validation path. The
proportional-treatment claim — Tier 1 and Tier 2 land in the same
downstream pipeline — depends on this. The test
`tests/test_batch_validation_uses_tier_1_models.py` asserts class
identity (the *same Python object*), not equivalence; a refactor that
forks the model is rejected at test time.

**Concurrency.** Concurrent batches from the same institution process
serially because the arq worker has a single FIFO queue. Per-
institution queue partitioning is a Part 9 production concern. The
sandbox FIFO is acceptable because (a) batches are infrequent
(typically once a day per institution); (b) the smoke-test demo flow
submits one batch at a time. Worth knowing for live-demo timing:
don't trigger two batches concurrently in the demo without
explaining the FIFO behaviour to the audience.

**Provenance.** A new `complaints.source` column (enum:
`api_realtime | batch`) records which path produced each complaint
row. Tier 1 POST writes `api_realtime`; the Tier 2 worker writes
`batch`. Existing rows backfill to `api_realtime` in the migration.

**Retries and dead-letter.** Transient failures (Postgres connection
drop, etc.) retry with exponential backoff. Dead-letter after 5
retries with batch status `failed`. Sandbox dead-letter surfacing is
"grep structlog for `batch.processing.failed`"; a Part 8 admin UI
exposes dead-lettered batches to SBS analysts directly.

## Precedent

[docs/research/market-comparators.md §5.B](../research/market-comparators.md#5b-event-driven-ingestion-layer)
is extended in this prompt to cover the worker-process variant
alongside the streaming variant, with a specific subsection on
async-worker patterns for regulator data ingestion.

The architectural pattern — HTTP endpoint enqueues, async worker
drains, status endpoint exposes state, webhook signals completion —
is the regulator-domain default for batch ingestion. UK Open
Banking's batch-submission flow follows this shape; the SEC's EDGAR
filing-submission system follows it; CFPB's bulk complaint upload
follows it. In each case the institution-facing surface is an
endpoint that returns "we have it" plus a way to find out what
happened, not a synchronous "here's the result of validating 50,000
rows" response.

The arq runtime choice cites arq's own documentation as the
implementation reference. The reasoning (asyncio-native, Redis as
backing store, durable across process restarts) follows the
canonical Python async-worker pattern as documented by arq's
maintainers and adopted in FastAPI's deployment guides.

## Divergence

This decision diverges from the FastAPI BackgroundTasks pattern that
many tutorials recommend for "fire and forget" work. We diverge
because BackgroundTasks is not durable: a uvicorn restart loses the
work. For a regulator system handling institutional submissions,
durability is non-negotiable.

We diverge from a synchronous validate-on-upload pattern (return the
validation result in the POST response body) because a 50,000-row
batch can take tens of seconds to validate row-by-row and would push
the HTTP request well past any institutional client's default
timeout. The asynchronous pattern is also the regulator-domain
default (Open Banking, EDGAR, CFPB bulk upload all use it).

We diverge from streaming validation (validate as bytes arrive). The
worker downloads the full CSV before validating. Streaming is a
Part 9 optimisation; the sandbox path is "store then process" which
is simpler to reason about and easier to debug.

We diverge from per-institution queue partitioning. The sandbox uses
a single FIFO queue. Per-institution partitioning is a production
concern (one slow institution should not delay another institution's
batch) and lands with the Part 9 worker fleet design.

## Consequences

- Worker process is a new operational surface in `docker-compose.yaml`
  (`sbs-suptech-sandbox-worker-1`). Operators need to understand it
  alongside the API container.
- Sandbox prune job (APScheduler entry, 7-day retention) manages
  local-filesystem hygiene. Production lifecycle policies replace it
  in Part 9.
- Same-validation-as-Tier-1 invariant is test-enforced. A refactor
  that forks Tier 1 and Tier 2 validation models breaks the test.
- Dead-letter surfacing in the sandbox is grep-based; a Part 8 admin
  UI exposes dead-lettered batches to SBS analysts directly.
- Both `process_batch` and `deliver_webhook` jobs share the same arq
  worker process and queue (FIFO). A long-running batch can delay a
  queued webhook delivery for an earlier batch's completion. This is
  sandbox-acceptable but worth knowing for live-demo timing — don't
  trigger two batches concurrently in the demo flow.
- The `complaints.source` column is the join key for any downstream
  analytics that need to know which ingestion path produced a row.
  ML training in Prompt 11 can use it to balance Tier 1 and Tier 2
  examples if the distribution skews.
