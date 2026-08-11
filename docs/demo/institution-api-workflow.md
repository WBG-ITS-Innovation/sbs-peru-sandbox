# Institution-to-SBS sandbox API — granular complaint workflow

This document explains how a synthetic institution sends one granular
Anexo-1A-like complaint to SBS over a real HTTP connection, and what
SBS does with it on receipt.

P11A.5a — sandbox infrastructure. The institution side is a CLI
running on the same laptop as the SBS API. The data the CLI sends is
synthetic. The connection, the institutional security chain, the
redaction, the data-quality checks, the audit chain, and the cockpit
SSE event are all real.

This complements the SUCAVE / statistical-reporting concepts the
sprint-input log already references. It does not replace SUCAVE
tomorrow. SUCAVE expects an aggregate Annex 1 report on a regulatory
cadence; this granular path is a complement that lets SBS see one
real-shaped complaint end-to-end inside the sandbox.

## What it is — and what it is not

It is sandbox infrastructure. The endpoint, the auth chain, the
redaction policy, the data-quality policy, the audit chain, the
cockpit SSE delta — all real.

It is not production SBS infrastructure. There is no live SBS
backend behind this URL. The cert chain is self-signed under
`dev-ca/`. The HMAC secret is a sandbox constant in
`scripts/dev-seed.sql`. The OAuth client secret is a sandbox constant
in `scripts/seed-oauth-clients.sh`.

## Endpoint

`POST /v1/sandbox/complaints/granular`

External, institution-facing. Sits next to `POST /v1/complaints`
(production-shaped Tier 1) and does not modify it. The `/sandbox/`
segment makes the URL space honest — the path is for sandbox
exercises with PII-bearing payloads. The production-shaped
`/v1/complaints` continues to accept the de-identified Tier 1
submission shape.

### Security chain (same as `/v1/complaints`)

1. **mTLS** — the institution presents `dev-ca/<institution>.pem`.
   The TLS handshake verifies the chain; the server resolves the
   `institution_id` from the `institution_certificates` row keyed
   by the certificate's SHA-256 thumbprint. For local plain-HTTP
   dev the CLI accepts `--insecure-skip-mtls` and instead sends a
   dev `X-Forwarded-Client-Cert` header (proxy-mode shape) carrying
   the same thumbprint. The server must be started with
   `SBS_API_MTLS_MODE=proxy` for this to be accepted. The header is
   attached to both `/v1/oauth/token` and
   `/v1/sandbox/complaints/granular` so the mTLS-keyed OAuth bucket
   and the mTLS-keyed business bucket both resolve the institution.
2. **OAuth 2.0 client_credentials** — `POST /v1/oauth/token` with
   HTTP Basic `client_id:client_secret` over the same mTLS
   connection. The returned JWT carries `cnf.x5t#S256` bound to the
   client's cert thumbprint.
3. **HMAC SHA-256** — `X-SBS-Signature: hmac-sha256-v1=<base64>` over
   the canonical request (method / path / lowercased-host /
   `X-SBS-Timestamp` / body-sha256-hex / `X-SBS-Institution-Id`).
   Per ADR 0027 amendment.
4. **Idempotency-Key** — required header. ADR 0029.

### Request body

The body is the same Anexo-1A-shaped payload the P11A internal demo
endpoint accepts (`DemoSubmissionRequest`). The narrative may
contain raw PII — names, DNI, phone, email, account/card numbers.
SBS redacts on receipt; raw PII is persisted only in
`raw_complaints`.

### Response — institution receipt

```json
{
  "submission_id": "<agent_run_id>",
  "institution_id": "SBS-001234",
  "complaint_id": "BCO-2026-1234567",
  "raw_complaint_id": "<uuid>",
  "status": "accepted" | "accepted_with_warnings" | "rejected" | "duplicate",
  "idempotency_key": "cli-...",
  "received_at": "2026-05-25T10:15:00+00:00",
  "timeline": [{"event": "received", "at": "...", "detail": "..."}, ...],
  "data_quality": {"errors": [], "warnings": [...], "suggested_enrichments": [...], "extracted_fields": {...}, "policy_version": "dq-demo-v1"},
  "redaction_policy_version": "redact-demo-v1",
  "data_quality_policy_version": "dq-demo-v1",
  "event_id": 42
}
```

`status` is derived from the data-quality report:

* `accepted` — no errors, no warnings.
* `accepted_with_warnings` — at least one warning, no errors.
* `rejected` — at least one DQ error (after structural validation
  passed). The complaint is still persisted with redacted text so
  the audit chain is consistent; the supervisor cockpit shows it
  with the warning state. Hard schema errors return 4xx before the
  orchestrator runs.
* `duplicate` — reserved for explicit duplicate detection. A
  same-key, same-body replay is signalled by the
  `Idempotency-Replayed: true` response header rather than the
  status field.

### What SBS does on receipt

The orchestrator from P11A (`run_demo_ingestion`) runs end-to-end:

1. Raw payload + raw narrative → `raw_complaints`. Storage policy
   `restricted-demo-pii-v1`. Only place raw PII lives.
2. Deterministic regex-and-allowlist redaction over narrative and
   response_detail (`sbs_api.redaction.engine`).
3. Canonical complaint persisted with redacted text only.
   `complaints.source = 'api_realtime'`.
4. Deterministic data-quality checks run against the redacted
   narrative plus the structured fields.
5. One `agent_runs` row written with the anonymizer tool_call and
   the DQ report in `final_output`. No raw PII.
6. Five `audit_events` rows written. No raw PII.
7. One `complaint.received` SSE delta published on the `cockpit`
   topic with the redacted card payload.

The supervisor cockpit at `/app/cockpit` shows the new card within
the SSE delivery window (best-effort).

The cross-source panel on that card will be **empty** for a freshly
submitted complaint: the correlator is replay-driven and falls back to
an intentionally blank default fixture. Demos that need a populated
cross-source panel or the anomaly card use the seeded golden complaint
`BCO-2026-000001`. See [docs/HANDOVER-NOTES.md](../HANDOVER-NOTES.md).

## Running the workflow

### 1. Start the API

```bash
bash scripts/dev-up.sh    # Postgres + Redis + migrations + seed

# Local sandbox smoke (plain HTTP, proxy-mode cert evidence).
SBS_API_MTLS_MODE=proxy PYTHONPATH="$PWD/api" bash scripts/run-api.sh
```

The dev-up script seeds the two demo institutions
(`SBS-001234` / `BANCO_DEMO_001` and `SBS-005678` / `COOPAC_DEMO_002`),
their HMAC secrets, their webhook secrets, and the demo OAuth
clients.

`SBS_API_MTLS_MODE=proxy` tells the API to resolve the
institution_id from the `X-Forwarded-Client-Cert` header (Envoy
de-facto shape) — what a real reverse-proxy in front of SBS would
forward after terminating mTLS. The institution CLI's
`--insecure-skip-mtls` flag is the local-smoke counterpart: it
sends that same header explicitly, carrying the dev cert's CN and
its SHA-256(DER) thumbprint.

The OAuth, HMAC, idempotency, and rate-limit chain are fully
enforced over plain HTTP in this mode. Only the TLS handshake
itself is bypassed.

For production-like mode, run the API behind a real TLS terminator
in `direct` or `proxy` mode against real client certificates, and
do **not** pass `--insecure-skip-mtls` to the CLI.

### 2. Start the supervisor cockpit (optional, to see the SSE delta)

```bash
cd app && npm install && npm run dev    # cockpit at http://localhost:3000/app/cockpit
```

The cockpit fetches server-to-server from an API on `:8000` and needs
Keycloak up for its session; `npm run dev` alone is not enough. Full
bootstrap — both API processes, the shared secret, and the demo-login
URL — is in the README's "Run the supervisor cockpit" section.

### 3. Send one complaint from the CLI

```bash
.venv/bin/python scripts/institution_push_demo.py \
    --api-base http://localhost:8000/v1 \
    --profile banco-tier1 \
    --scenario wallet-misclassified \
    --insecure-skip-mtls
```

Other scenarios:

```bash
# DQ warnings (missing product / motive codes)
.venv/bin/python scripts/institution_push_demo.py \
    --scenario missing-required-field --insecure-skip-mtls

# Idempotent retry — same Idempotency-Key, same body, FRESH HMAC signature.
# Expected: second send returns the original receipt; no second canonical
# complaint is created.
.venv/bin/python scripts/institution_push_demo.py \
    --scenario duplicate-retry --insecure-skip-mtls

# Security-rejection demo — exact HMAC signature replay (same canonical
# request bytes). Expected: HTTP 401 SIGNATURE_REPLAYED on the second
# send. This is the backend's anti-replay protection, not the idempotency
# retry path.
.venv/bin/python scripts/institution_push_demo.py \
    --scenario hmac-replay-attack --insecure-skip-mtls
```

### Scenario semantics

| Scenario | First send | Second send | Expected |
|---|---|---|---|
| `wallet-misclassified` | one signed POST | — | 201 `accepted` or `accepted_with_warnings` |
| `missing-required-field` | one signed POST | — | 201 with `status="rejected"` (DQ errors) |
| `duplicate-retry` | fresh signature, idem key X, body B | **fresh signature** (new timestamp / nonce), **same** idem key X, **same** body B | 201 — same `complaint_id` returned, no second canonical row |
| `hmac-replay-attack` | fresh signature | exact signature replay (reused timestamp + body) | 401 `SIGNATURE_REPLAYED` |

The `duplicate-retry` path exercises the institution's correct
behaviour after a network glitch: replay the same logical request
with the same `Idempotency-Key` and the same body, but sign it
afresh (new nonce in the form of a microsecond-precision
`X-SBS-Timestamp`). The `hmac-replay-attack` path exercises the
server's defence: if the *exact same signed bytes* arrive twice, the
replay cache rejects the second one.

### 4. (Optional) curl equivalent

For day-to-day smoke runs use the signed CLI
([scripts/institution_push_demo.py](../../scripts/institution_push_demo.py)).
It is the canonical local-smoke client — it computes the XFCC header,
the HMAC signature, and the Idempotency-Key consistently with the
server-side dependencies, and it masks PII in printed traces.

If you need a raw curl walk-through (e.g. for an SDK author who is
porting the signing convention to another language), assemble it
from a local, non-committed config file. Never paste real
credentials into committed docs.

Recommended local layout (kept out of git via `.gitignore`):

```text
local/sandbox-smoke.env       # CLIENT_ID, CLIENT_CREDENTIAL, HMAC_SECRET_HEX, INSTITUTION_ID
```

The four values are sourced from the sandbox onboarding outputs you
already have on disk:

* `CLIENT_ID` / `CLIENT_CREDENTIAL` — issued by
  `scripts/seed-oauth-clients.sh` and surfaced in its stdout.
* `HMAC_SECRET_HEX` — read from the `institution_secrets` row your
  local Postgres holds (`psql -c "SELECT encode(active_secret,'hex')…"`).
* `INSTITUTION_ID` — the sandbox institution id you authenticated as
  (e.g. the one bound to the dev cert via `dev-ca/thumbprints.txt`).

With those exported into the shell, the shape of a signed POST is:

```bash
# Source local-only credentials. Never commit this file.
set -a; . ./local/sandbox-smoke.env; set +a

# 1. Token (HTTP Basic over plain HTTP, proxy-mode XFCC simulated).
ACCESS_TOKEN=$(
  curl -sS \
    -u "$CLIENT_ID:$CLIENT_CREDENTIAL" \
    -H "X-Forwarded-Client-Cert: $XFCC" \
    -d "grant_type=client_credentials&scope=complaints:write" \
    http://localhost:8000/v1/oauth/token \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

# 2. Compose canonical request + sign with HMAC_SECRET_HEX from env.
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%S.%6NZ)
BODY='{"institution_id":"'"$INSTITUTION_ID"'","narrative":"Hello, sandbox."}'
BODY_HASH=$(printf '%s' "$BODY" | openssl dgst -sha256 -hex | sed -E 's/^.*= //')
HOST_HEADER="localhost:8000"
CANONICAL=$'POST\n/v1/sandbox/complaints/granular\n'"$HOST_HEADER"$'\n'"$TIMESTAMP"$'\n'"$BODY_HASH"$'\n'"$INSTITUTION_ID"
SIG=$(printf '%s' "$CANONICAL" \
    | openssl dgst -sha256 -mac HMAC -macopt hexkey:"$HMAC_SECRET_HEX" -binary \
    | base64)

# 3. POST. XFCC is the proxy-mode local-smoke equivalent of mTLS.
curl -sS -X POST http://localhost:8000/v1/sandbox/complaints/granular \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: curl-$(date +%s)" \
    -H "X-SBS-Timestamp: $TIMESTAMP" \
    -H "X-SBS-Signature: hmac-sha256-v1=$SIG" \
    -H "X-SBS-Institution-Id: $INSTITUTION_ID" \
    -H "X-Forwarded-Client-Cert: $XFCC" \
    --data "$BODY"
```

`XFCC` is the Envoy XFCC string the CLI builds. To match it exactly,
copy what `scripts/institution_push_demo.py` prints in its `[1/6]`
step, or build it yourself:

```text
Hash=<sha256-hex of the leaf DER>;Subject="CN=<institution CN>,O=SBS";URI=
```

The thumbprint is the value `dev-ca/thumbprints.txt` lists for your
institution; the CN is the dev-leaf CN (e.g. `BANCO_DEMO_001`). For
real mTLS, the proxy populates this header from the verified peer
cert and you do not set it manually.

## Demo script (two-pane)

Left pane — institution terminal:

```bash
.venv/bin/python scripts/institution_push_demo.py \
    --profile banco-tier1 --scenario wallet-misclassified --insecure-skip-mtls
```

Right pane — supervisor cockpit:

```
http://localhost:3000/app/cockpit
```

Watch the cockpit pick up the new card on the `complaint.received`
SSE delta. The narrative on the card is the redacted text; raw PII
never reaches the browser.

## PII safety guarantees

* Raw narrative + raw payload — `raw_complaints` only. Storage
  policy `restricted-demo-pii-v1`.
* Canonical complaints, agent_runs, audit_events, cockpit SSE,
  the HTTP response body, and the CLI's printed trace are PII-free.
* The CLI masks DNI, phone, email, full name, and account/card
  numbers before printing the request/response. The on-wire body
  is unchanged — the server expects PII and redacts on receipt.

## Failure modes (negative tests)

* Missing OAuth token → 401 `TOKEN_REQUIRED` / `TOKEN_INVALID`.
* Bad HMAC signature → 401 `SIGNATURE_INVALID`.
* Missing `X-SBS-Signature` or `X-SBS-Timestamp` → 401
  `SIGNATURE_MISSING_HEADER`.
* Missing `X-SBS-Institution-Id` → 401 `SIGNATURE_MISSING_HEADER`.
* Tenant mismatch (body `institution_id` ≠ authenticated caller) →
  404 (does not leak tenant existence).
* Replayed signature → 401 `SIGNATURE_REPLAYED`.
* Missing `Idempotency-Key` → 422 from FastAPI's header validation.
* Same key, different body → 409
  `IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_BODY`.

## Relationship to SUCAVE

SUCAVE is the existing SBS aggregate-reporting platform. Institutions
submit an aggregate Annex 1 report on a regulatory cadence. This
granular sandbox endpoint is a complement: it shows that a single
real-shaped complaint can travel from an institution to SBS over a
real signed connection, be redacted, be quality-checked, and surface
on a supervisor cockpit in near-real-time. It does not replace
SUCAVE and does not promise that SBS will accept granular complaints
in production tomorrow.

## ADR pointers

* ADR 0027 amendment — HMAC canonical-request signing.
* ADR 0029 — Idempotency-Key.
* ADR 0031 — mTLS subject extraction.
* ADR 0032 — OAuth 2.0 client_credentials + cert-binding.
* ADR 0044 — deterministic PII redaction (P11A).
* ADR 0045 — deterministic data-quality checks (P11A).
