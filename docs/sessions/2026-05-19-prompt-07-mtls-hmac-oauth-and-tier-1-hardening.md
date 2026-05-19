# Session journal — 2026-05-19 — mtls-hmac-oauth-and-tier-1-hardening

- **Date:** 2026-05-19
- **Prompt #:** 7
- **Part:** 3 (closing — first time)
- **Branch:** `part-03/mtls-hmac-oauth-and-tier-1-hardening`
- **PR:** _filled in by the closeout commit + PR-open step_
- **Cross-review:** [docs/reviews/2026-05-19-docs-adr-003-123.md](../reviews/2026-05-19-docs-adr-003-123.md)
- **Slug:** mtls-hmac-oauth-and-tier-1-hardening
- **Files touched:** 92 (across 14 commits) — 11,019 insertions, 537 deletions on this branch vs main.

## What landed

Part 3 closes for the first time. The institution-facing API now stands up the full auth chain end-to-end: mTLS at the TLS layer authenticates the institution by certificate, OAuth 2.0 client_credentials issues a cert-bound JWT carrying explicit scopes, HMAC SHA-256 signs each unsafe request, and a Redis-backed token-bucket enforces per-institution rate limits with the four `X-RateLimit-*` headers on every response. Three new ADRs (0031, 0032, 0033) lock the contract; four amendments to existing ADRs (0027 HMAC canonical request, 0028 ×4, 0029 ×2) fill in what was previously TBD. A dev CA script issues root + two client certs + a sandbox server cert; `dev-up.sh` bootstraps the whole stack in one command. The idempotency policy gains a `state` column and a placeholder-INSERT pattern for concurrent duplicate POSTs (the ADR 0029 amendment). An auth-chain smoke test (`scripts/smoke-test-auth.sh`) exercises the full signed-request path against the running API — mTLS handshake, OAuth token with `cnf.x5t#S256` verified against the cert thumbprint, signed POST returning 201 with rate-limit headers, replay rejected as `SIGNATURE_REPLAYED`, and a 429 with `Retry-After` once the per-institution bucket is exhausted.

Test count: **219 → 320** (+101). Workstream commits on the branch (oldest → newest):

| Commit | Workstream | Headline |
| --- | --- | --- |
| c5f5315 | A0 | Three new ADRs + four amendments (single commit at branch head) |
| 94d2495 | pressure-test | Pre-workstream-A pressure-test amendments |
| 364d691 | A | mTLS termination + dev CA |
| 2e01c2e | B | HMAC verification dependency |
| 75862b8 | C | OAuth 2.0 client_credentials flow |
| 6512a51 | D | Idempotency sweep job (APScheduler in lifespan) |
| 456ec0b | E | Per-institution + token-endpoint rate limiter |
| 6607848 | F.1/F.2/F.3 | Idempotency state column + middleware reorder + chunked-read |
| f2c7276 | F.4/F.5/F.6 | 500 exc_info + cursor signing + smoke-reset env gate |
| b402e5f | F.7 | Auth-stub migration on protected routes |
| a8ea03a | G | Auth-chain smoke test + one-command bootstrap |
| 2b6f4c0 | H disposition | Closeout fix-now items (HMAC wiring, SSL kwargs, auth-failure logging, etc.) |

## Cross-model review — triage line

Cross-review against Azure OpenAI (deployment `gpt-5.4`) on the three new ADRs:

- Six findings dispositioned: **3 accept-in-prompt** (RFC 8705 thumbprint encoding noted in ADR 0031 with Day-2 migration path; OpenAPI spec scope identifiers aligned to ADR 0032; batch-upload bypass noted as future-amendment trigger in ADR 0033). **3 defer-to-day-2** (CN-vs-SAN identity convention review; JWT `kid` resolver for non-breaking key rotation; audit-log table model as Part 6 deliverable). All deferrals listed in `docs/DEFERRED.md` "Prompt 7 closeout — Day-2 review-disposition deferrals". The deeper-reasoning second-pass deployment (`AZURE_OPENAI_DEPLOYMENT_DEEP`) was not set in this shell; the spec's lighter-harness commitment treats that pass as optional and is satisfied by the single pass on the load-bearing security ADRs.

## Adversarial review — strongest objection

Second-opinion (adversarial subagent) — strongest finding: **the auth chain produced clean ProblemDetail responses on every failure but emitted zero structured log records for 401/403/429.** A regulator demoing on May 25 who asked "show me yesterday's failed-auth attempts on the sandbox" would have got nothing; brute-force probes against `client_secret` would have been invisible until the 50/min token-endpoint bucket fired (and that 429 was also silent). Mitigation landed in H disposition (`sbs_api_exception_handler` now emits `auth_failure` with code/status/method/path/correlation_id/traceparent on every 401/403/429). Two further fix-nows from the same agent landed in the same commit: the idempotency sweep no longer deletes rows in `state='processing'` (was destroying audit evidence of orphaned handlers and could break the idempotency contract for slow handlers); the HMAC `host` fallback to `"testserver"` is confined to `environment=="test"` (was a canonicalisation-ambiguity production path).

## Subagent verdicts

| Subagent | Verdict | Headline finding (disposition) |
| --- | --- | --- |
| reviewer | BLOCK → APPROVE after disposition | HMAC dep defined but not wired; run-api.sh SSL kwargs not read; NULL rate_limit_per_minute → 500; OpenAPI scope drift; smoke-test.sh broken by F.7. All five **fixed in 2b6f4c0**. |
| architect-guard | APPROVE WITH AMENDMENT | No silent ADR divergence. Three nits: legacy `get_auth_context` stub uses dot-separated scopes (dead code); `mtls_mode` defaults to `disabled`; `CertCnUnknown` raised on thumbprint mismatch (semantic off-by-one in name). All deferred to Part 8 cleanup. |
| doc-sync | BLOCK → APPROVE after disposition | Error-catalog hard numeric collisions (SBS-401-001..003, SBS-403-001..002, SBS-409-003); README quickstart stale; CONTRIBUTING "until Prompt 7" line; PLAN.md Part 3 still all `[ ]`. All **fixed in 2b6f4c0**. |
| regulator-readability | APPROVE WITH NITS | No banned phrasing, no "real-time" misuse, no "pilot bank". Five docs nits (CN/SAN/CRL/OCSP first-use; `cnf.x5t#S256` gloss; `~10k/day` label; 600s+30s arithmetic; "second-opinion subagent expected to flag it" wording). All **applied in 2b6f4c0**. |
| benchmark-checker | APPROVE WITH NITS | All six ADRs cite a specific section of `docs/research/market-comparators.md` (§5.A.M for the auth-chain ADRs; §5.A and §2.1 for the pre-existing ones). One optional nit (ADR 0028 cursor-signing amendment cite AWS SigV4 §Task 1). **Applied in 2b6f4c0.** |
| second-opinion | WEAKNESS-FLAGGED | Three fix-now items (auth-failure logging gap; sweep state-filter bug; HMAC host-fallback ambiguity) — **all applied in 2b6f4c0**. Five defer-to-day-2 items (test-fixture blanket-override blind spot; `kid` resolver; Lua clock source; `disable_mtls_for_tests` env guard; secret hygiene `dev-ca/.gitignore`) — **all listed in DEFERRED.md**. |

## Decisions locked

- mTLS client identity per ADR 0031 (CN is the institution identifier; XFCC `Hash=`/`Subject=` in proxy mode satisfies RFC 8705 §3.2 cert-binding).
- OAuth 2.0 client_credentials per ADR 0032 (four scopes: `complaints:write`, `complaints:read`, `batch:upload`, `status:read`; 15-minute JWT TTL; `cnf.x5t#S256` cert-bound; `kid=sandbox-v1` from day one).
- Rate limiting per ADR 0033 (per-institution token bucket on Redis; tier defaults large=1000/min small=100/min; per-institution override on `institutions.rate_limit_per_minute`; separate 50/min bucket on `/v1/oauth/token` keyed on mTLS CN).
- HMAC canonical request shape per ADR 0027 amendment (six lines: method / target / lowercased Host / timestamp / body-hash / institution_id; `hmac-sha256-v1=` prefix; 5-minute skew; 10-minute Redis replay window).
- Cursor pagination signed per ADR 0028 amendment (HMAC-SHA256 over the JSON payload with a server-side master key; constant-time compare; tampered cursors return 400 `CURSOR_INVALID`).
- Concurrent-POST idempotency per ADR 0029 amendment (`state` column; placeholder INSERT under unique constraint; 50ms × 3 retry; 409 `IDEMPOTENCY_KEY_IN_FLIGHT` on persistent in-flight conflict).
- Middleware order reversed for the 413 path per ADR 0028 amendment (body_size_limit is innermost; 413 ProblemDetail now carries `X-Correlation-Id` and `traceparent`).
- Auth-failure observability hook per workstream-H disposition (`sbs_api_exception_handler` emits `auth_failure` event for every 401/403/429 ProblemDetail).

## Decisions deferred (to a named future prompt / part)

Documented in `docs/DEFERRED.md` "Prompt 7 closeout — Day-2 review-disposition deferrals":

1. **RFC 8705 base64url thumbprint encoding** — Part 9 alongside HS256→RS256.
2. **JWT `kid` resolver for non-breaking key rotation** — Part 9.
3. **Rate-limit Lua script clock source** (Python `time.time()` → Redis `TIME`) — Part 9 when multi-replica lands.
4. **Test-fixture blanket-override conformance test** — Part 7 / Day-2 hardening.
5. **Secret hygiene `dev-ca/.gitignore` + SECURITY.md leakage section** — Day-2 hardening.
6. **Audit-log subsystem** — Part 6 (auth-failure structlog hook is the bridge).
7. **OpenAPI match test on `oauth_clients` / `institution_certificates` / `institution_secrets` and the scope set** — Part 7 with standards-pack cut.
8. **`disable_mtls_for_tests` environment guard** — Day-2 hardening.
9. **`oauth_clients.cert_thumbprint_required` seeding** — Part 8 admin-API onboarding flow.

Plus the architect-guard observations (legacy `get_auth_context` dead-code cleanup; `CertCnUnknown` semantic-off-by-one rename) and the pressure-test deferrals (audit logging proper, GET-body rejection, HMAC secret rotation endpoints, OpenAPI auth gating decision, webhook signing for outbound callbacks) already listed in DEFERRED.md.

## Decisions flagged for cross-model review

- The auth-chain ADRs were cross-reviewed via Azure OpenAI on 2026-05-19; output at `docs/reviews/2026-05-19-docs-adr-003-123.md`. No follow-up flagged for further model review.
- The CN-vs-SAN identity convention (raised by the cross-review's strongest disagreement-with-primary) is a regulator-policy question more than a model question; flagged for Sergio/Mariela conversation before Part 9.

## Paste-ready block for the maintainer

> Prompt 7 closed. Branch: `part-03/mtls-hmac-oauth-and-tier-1-hardening`. PR: <url filled after PR open>. Locked: mTLS + HMAC + OAuth + rate-limiter end-to-end (ADRs 0031/0032/0033 Accepted; four amendments to 0027/0028/0029); auth-stub migration on protected routes; auth-chain smoke test green via `bash scripts/smoke-test-auth.sh`. Test count 219 → 320. Deferred to Day 2: RFC 8705 base64url thumbprint, JWT kid resolver, Lua-script Redis clock, test-fixture conformance check, dev-ca .gitignore + SECURITY.md, audit-log subsystem, OpenAPI match test on operator tables, mTLS-test env guard, cert_thumbprint_required seeding. Next prompt opens with `/part-start 4`.

## Notes

- The H disposition commit (2b6f4c0) bundles thirteen distinct fixes that the six subagents and the cross-review surfaced. They are itemised in the commit message; the journal table above is the audit-trail-friendly summary.
- `scripts/smoke-test.sh` is now an auth-free subset (liveness, ProblemDetail shape, body-size 413 with `X-Correlation-Id` per ADR 0028 F.2, canonical YAML reachability, `traceparent` echo). The full signed-request path requires `scripts/smoke-test-auth.sh`. README and CONTRIBUTING reflect the split.
- The deeper-reasoning Azure deployment (`AZURE_OPENAI_DEPLOYMENT_DEEP`) was not provisioned in this shell. The spec's lighter-harness commitment makes that pass optional; the single cross-review on the three new ADRs (gpt-5.4) satisfied the gate.
- The cursor-signing key + the OAuth signing key live on disk under `dev-ca/`. Both are sandbox-grade; the production posture (Key Vault, hardware-backed) is the Part 9 deliverable. The Day-2 DEFERRED.md item names the hygiene step (`dev-ca/.gitignore` with `*`) for any contributor who regenerates these files into a non-default path.
- Wall-clock from the F entry status checkpoint to this journal: ≈75 minutes including 6 subagent runs in parallel, the Azure cross-review (one TLS-bundle retry via `/tmp/sbs-combined-ca.pem`), 13 disposition fixes, and final suite re-run.
