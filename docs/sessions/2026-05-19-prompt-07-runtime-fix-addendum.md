# Session journal addendum — 2026-05-19 — prompt-07 runtime fix

This addendum supplements the primary session journal
(`2026-05-19-prompt-07-mtls-hmac-oauth-and-tier-1-hardening.md`). The
primary journal recorded the H closeout disposition assuming the PR
would open cleanly. Two things happened after that point that the
journal did not anticipate; this addendum is the durable record.

## Runtime debug — uvicorn ASGI TLS extension gap

After the H disposition commit landed (`2b6f4c0`), end-to-end smoke
testing against the live stack revealed that the auth chain failed at
the first authenticated endpoint with `401 CERT_REQUIRED`, despite a
successful mTLS handshake at the TLS layer. Root cause: uvicorn 0.47
does not implement the ASGI TLS extension. The peer cert is verified
at the TLS layer but never surfaced into `scope['extensions']['tls']`,
which `_direct_mode_extract` was reading. The unit and integration
tests passed because they injected directly into that scope key; only
real uvicorn exposed the gap.

Fix: new ASGI middleware
(`api/sbs_api/middleware/mtls_transport.py`) walks the asyncio task's
coroutine frames to find uvicorn's `RequestResponseCycle`, pulls the
peer cert DER off
`transport.get_extra_info("ssl_object").getpeercert(binary_form=True)`,
stashes on `scope['state']['peer_cert_der']`. `_direct_mode_extract`
in `api/sbs_api/dependencies/mtls.py` rewritten to read from
`request.state.peer_cert_der`. Middleware registered in
`api/sbs_api/app.py` as the outermost layer so it captures cert state
before any other middleware muddies the call stack.

Three further bugs surfaced during the end-to-end debug, all fixed in
the same PR:

- **HMAC canonical-request Host mismatch.** The smoke script signed
  against `$HOST` without the port; curl with `--resolve` sent
  `Host: sbs-suptech-sandbox.local:8443`. Fixed by introducing
  `$HOST_HEADER = "${HOST}:${PORT}"` in `scripts/smoke-test-auth.sh`
  and signing against that.
- **POST 201 missing rate-limit headers.** `business_bucket` set
  `X-RateLimit-*` on the injected `Response`, but the handler returned
  a fresh `JSONResponse` for the 201 + Location pattern which
  discarded those headers. Fixed by merging `response.headers` into
  the returned `JSONResponse`'s headers (with `setdefault` so
  handler-set Location and ETag take precedence).
- **Four mTLS dependency tests broke** because they injected via the
  old `scope['extensions']['tls']['client_cert_chain']` path. Rewrote
  to inject `request.state.peer_cert_der` with DER bytes, simulating
  what the middleware would have done in production.

Status: all five `scripts/smoke-test-auth.sh` assertions pass
end-to-end against the live API. The auth chain claim is now
verifiable: mTLS handshake → cert extraction via middleware → cert
lookup in `institution_certificates` → OAuth scope intersection →
cert-bound JWT issuance → HMAC signature verification → idempotency
state machine → rate-limit token bucket → response with the four
`X-RateLimit-*` headers.

## Caveat — uvicorn internals are private surface

`MtlsTransportCaptureMiddleware` reaches into uvicorn-private state
(walks frames to find `RequestResponseCycle.transport`). This is a
known-fragile seam. Part 9 will either upgrade to a uvicorn release
that ships the standard ASGI TLS extension, or migrate the serve
layer to hypercorn (which already exposes
`scope['extensions']['tls']`). Until then, this middleware is the
bridge. Added to `docs/DEFERRED.md` Day-2 list.

## PR #33 squash-merge dropped most of the workstream code

Discovered during the merge-conflict cleanup of PR #34 that PR #33
(merged earlier as `627091e`) lost approximately 3,700 lines of code
during its squash merge. The squash commit message lists workstreams
A–G and the H closeout disposition, but the actual squashed tree
contained only the A0 ADR commit plus the original pre-Prompt-7
auth-stub code. Workstream B (HMAC), C (OAuth), D (sweep), E (rate
limiter), F (hardening), G (smoke test), and H (closeout disposition)
were all absent from main after the squash.

This was not caused by anything the operator or the closeout pipeline
did wrong; it appears to be a squash-merge artefact where conflict
resolution during the squash picked older versions of multiple files.
The exact mechanism is not yet understood and is documented for
discussion with the WBG engagement manager and the WBG technical lead.

Resolution path: PR #35 was opened against main containing the full
working tree from branch
`part-03/mtls-hmac-oauth-and-tier-1-hardening` (the working state from
which the smoke test passed), plus the runtime fix described above.
PR #34, which had conflicted because its base assumed PR #33 had
delivered the code that turned out to be missing, was closed in
favour of #35.

## Recommendation for the repo

Switch the default merge style for large multi-file PRs from squash
to merge-commit or rebase-merge. The Prompt 7 work was 13 commits
across 12 days of careful workstream sequencing; collapsing that into
one squash discarded the intermediate commit boundaries that would
have made the merge result reviewable. Squash works well for small
fix-it PRs; it does not scale to architectural multi-workstream
deliveries.

Filed as a Day-2 conversation in `docs/DEFERRED.md`.

## Wall clock

Primary journal closed at ~04:51 UTC. Runtime debug ran from ~04:53
to ~07:30 UTC (≈2.5 hours, including the PR #33 squash discovery and
PR #35 recovery). Final state: PR #35 open and awaiting review; PR
#34 closed; all tests passing; smoke test green; infra torn down.
