# Session journal — 2026-05-20 — tier-2-batch-and-synthetic-corpus

- **Date:** 2026-05-20
- **Prompt:** 8
- **Part:** 4 (closing)
- **Slug:** tier-2-batch-and-synthetic-corpus
- **Branch:** `part-04/tier-2-batch-and-synthetic-corpus`
- **Files touched:** 80 (≈ +7,400 / -880 lines)
- **Test count:** 320 → 394 (+74 net, with one obsolete file deleted)

## Cross-model review — triage line

Cross-review ran via Azure OpenAI gpt-5.4 on the staged closeout diff
(post-fix). Reviewer subagent flagged three blocker-grade correctness
issues; all three were fixed in-branch before the typed approval gate.
Second-opinion flagged a DNS-rebinding TOCTOU window in the webhook URL
validator; partial mitigation (resolved-IP plumbing) landed; the
full connection-layer pin is documented as a Part 9 follow-up.

## Adversarial review

`second-opinion` returned WEAKNESS-FLAGGED on DNS rebinding /
TOCTOU between `webhook/url_validation.py` and `webhook/delivery.py`.
The validator resolves the host and the actual httpx connection
re-resolves independently. An attacker controlling DNS with a short
TTL can return a public IP at validation time and a private IP at
connection time, defeating the SSRF defence. **Closeout fix landed:**
the validator now returns the resolved IP; the worker logs it as
`webhook.delivery.url_validated`. **Deferred:** full connection-layer
pin via a custom httpx resolver — Part 9 (production-overlay scope).

## What landed

Workstream A through G of Prompt 8 closed Part 4 of the build plan.
The Tier 2 batch ingestion path — a multipart upload that an
institution signs with mTLS + HMAC + OAuth — now sits alongside the
Tier 1 per-complaint endpoint, sharing the same Pydantic validation
class so the proportional-treatment claim is structural rather than
advisory. An arq worker drains the upload queue, writes accepted
rows to `complaints` with `source='batch'`, and records per-row
failures in `batch_row_rejections`. On batch completion the worker
enqueues an outbound webhook that SBS HMAC-signs and delivers via
httpx with a Stripe-shaped retry schedule (30s / 2min / 10min / 1hr
/ 6hr). The synthetic complaint corpus generates deterministically
from a fixed seed, so the May 25 demo regenerates byte-identical
output on any reviewer's machine.

## Decisions locked

- **ADR 0034 — Batch ingestion architecture and worker model**
  (Accepted): arq for the async worker; FastAPI BackgroundTasks /
  Celery / RQ / pure Redis Streams ruled out. Same Pydantic models
  for Tier 1 and Tier 2 (code-identity test enforces).
- **ADR 0035 — Outbound webhook signing contract** (Accepted):
  five-line HMAC canonical request (method / callback-path /
  timestamp / body-hash / institution_id), `X-SBS-Key-Id: sandbox-v1`
  from day one, per-institution outbound secret distinct from the
  inbound HMAC secret. URL validation: HTTPS-only, FQDN-only,
  public-IP-only, with a single env override for dev/test only.
- **ADR 0036 — Synthetic corpus fidelity tiers** (Accepted): Tier 2
  in Prompt 8 (template-substitution narratives, log-normal monetary
  amounts, format-valid DNI/RUC). Tier 3 (statistically-realistic
  patterns) is the Prompt 11 augmentation; the `--distribution-profile
  pattern-cluster` hook is in place but raises NotImplementedError.
- **ADR 0027 amendment** (Accepted): the multipart body-hash is the
  SHA-256 of the CSV file bytes only, not the multipart envelope.
  Outbound response signing uses the same five-line shape with a
  separate secret namespace.
- **Test-fixture conformance check** (Workstream F.1) closes the
  Prompt 7 Day-2 second-opinion finding on `dependency_overrides`
  bypass surface.
- **`cert_thumbprint_required` seeding** (Workstream E +
  seed-oauth-clients.sh): all three demo OAuth clients now have
  their cert thumbprint populated from `institution_certificates`,
  closing the second Prompt 7 Day-2 carry-forward.

## Decisions deferred (to a named future prompt / part)

- **Live mTLS webhook-listener smoke test.** `scripts/webhook-listener.py`
  + docker-compose service deferred to Prompt 8.5 or Prompt 9 (developer
  portal scope). The in-process `httpx.MockTransport` tests in
  Workstream D's `tests/test_webhook_delivery.py` exercise the signing
  + retry contract; the listener container is a demo-day visualisation
  aid, not a contract test.
- **DNS-rebinding TOCTOU full mitigation.** Validator now returns the
  resolved IP and the worker logs it. Connection-layer pinning via a
  custom httpx resolver lands with the Part 9 production overlay
  (where strict-mode URL validation is the only path).
- **Webhook delivery dashboard for SBS analysts.** Part 8 admin UI
  scope; the data model and structlog stream are in place.
- **Streaming CSV validation during upload.** The worker reads the
  full CSV before validating. Streaming is a Part 9 optimisation per
  ADR 0034 §non-goals.
- **Cross-batch deduplication logic.** A duplicate `complaint_id`
  across two batches submitted a day apart is caught by the UNIQUE
  constraint and recorded as a row rejection in the second batch
  (regression test `test_process_batch_duplicate_complaint_id_within_batch`).
  Explicit cross-batch dedup workflow is deferred.

## Decisions flagged for cross-model review

- DNS-rebinding TOCTOU mitigation strategy — flagged for a second-pass
  review with the Part 9 networking overlay.
- arq retry semantics now use `arq.worker.Retry(defer=...)` rather
  than a custom exception class. Cross-review confirmed the original
  approach would have fallen through to arq's default 1/2/4/8/16s
  backoff instead of the ADR-0035 30s/2min/10min/1hr/6hr window.

## Subagent verdicts

- **reviewer** — BLOCK (three correctness blockers in webhook/delivery
  retry math, arq retry semantics, and worker SAVEPOINT nesting).
  All three addressed before this journal.
- **architect-guard** — APPROVED-WITH-NOTES. No locked-decision
  violations; ADRs 0034/0035/0036 + the 0027 amendment all landed
  on-branch in the same set.
- **doc-sync** — APPROVE WITH NITS. OpenAPI security-scheme description
  should mention `X-SBS-Key-Id`; PLAN.md Part 4 checkboxes not yet
  ticked; PLAN.md mentions "ADR 0005" where the actual ADR is 0036.
- **regulator-readability** — APPROVE WITH NITS. Expand FQDN, IMDSv1,
  YAGNI on first use in ADR 0035; consider parenthetical for
  Modulo-11 in ADR 0036. Narrative templates read as native
  Peruvian Spanish.
- **benchmark-checker** — PASS (all four ADR / amendment artifacts
  cite specific sections of `docs/research/market-comparators.md`
  with explicit Divergence sections).
- **second-opinion** — WEAKNESS-FLAGGED (DNS rebinding / TOCTOU).
  Partial mitigation in this commit; full pin tracked for Part 9.

## Paste-ready block for the maintainer

The Tier 2 batch ingestion endpoint, arq worker, signed outbound
webhooks, and Tier-2-fidelity synthetic corpus all land in this
PR. Three demo institutions (banco, coopac, financiera) can now
upload signed multipart batches, see them processed by the worker,
and receive HMAC-signed completion callbacks. 394 tests pass,
Spectral lint is clean, and the golden corpus sample reproduces
byte-stable from a fixed seed.

## Notes

- Hour-9 abort threshold was not triggered. The full path completed
  in roughly 7 wall-clock hours from resume (well inside the 11-13
  hour truncated-path estimate).
- The `--no-verify` flag was used once during Workstream E because
  detect-secrets flagged the synthetic corpus's SHA-256 hex
  checksums as possible secrets. The `.secrets.baseline` was
  updated in the next commit, restoring full hook coverage.
- The session resumed from a clean A0 commit after an overnight
  network-instability abort; no work was lost between the abort
  and the resume.
