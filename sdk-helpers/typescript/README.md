# `@sbs/webhooks-helper` — TypeScript webhook verification

Hand-maintained webhook signature verification for the SBS SupTech
Complaints API. Uses **only `node:crypto`** from the standard Node.js
library — no external dependencies. Ships as **dual ESM + CJS** so
modern and legacy Node.js environments are both covered without
adoption friction.

See [ADR 0038](../../docs/adr/0038-sdk-helper-scope-and-distribution.md)
for the design rationale and [ADR 0035](../../docs/adr/0035-outbound-webhook-signing-contract.md)
for the canonical-request contract this helper implements.

## What it does

Verifies the `X-SBS-Signature`, `X-SBS-Timestamp`, and `X-SBS-Key-Id`
headers attached to outbound webhook callbacks from the SBS sandbox.
On success, returns nothing. On failure, throws one of:

- `SignatureExpiredError` — timestamp outside the ±5-minute clock-skew
  window, or malformed.
- `KeyIdUnknownError` — `X-SBS-Key-Id` is not `sandbox-v1`.
- `SignatureInvalidError` — HMAC SHA-256 over the canonical request
  did not match, or the signature header lacks the `hmac-sha256-v1=`
  prefix.

All three extend `WebhookVerificationError`.

## What it does NOT do

This helper is intentionally tiny. It is **not** a full client SDK; it
does not generate API clients, handle OAuth tokens, manage mTLS
certificates, or implement replay protection (replay is the receiver's
responsibility — track recently-seen `(timestamp, signature)` pairs
within the skew window).

For client-code generation in Java / C# / Go, see the OpenAPI
Generator recipes in `standards-pack/recipes/`.

## Usage

```ts
import {
  verifyWebhookSignature,
  SignatureInvalidError,
  SignatureExpiredError,
  KeyIdUnknownError,
} from '@sbs/webhooks-helper';

const YOUR_OUTBOUND_SECRET = Buffer.from(process.env.SBS_OUTBOUND_SECRET!, 'utf8');
const YOUR_INSTITUTION_ID = 'SBS-001234';

export function handleSbsCallback(req: express.Request, res: express.Response): void {
  try {
    verifyWebhookSignature({
      secret: YOUR_OUTBOUND_SECRET,
      keyId: req.header('X-SBS-Key-Id')!,
      timestamp: req.header('X-SBS-Timestamp')!,
      rawBody: req.body,                  // Buffer — see "raw body" below
      signatureHeader: req.header('X-SBS-Signature')!,
      method: req.method,
      callbackPath: req.originalUrl,
      institutionId: YOUR_INSTITUTION_ID,
    });
  } catch (err) {
    if (err instanceof SignatureExpiredError
        || err instanceof SignatureInvalidError
        || err instanceof KeyIdUnknownError) {
      res.status(401).end();
      return;
    }
    throw err;
  }
  // Signature good — process the payload.
  res.status(200).end();
}
```

### Critical: pass the EXACT raw body bytes

`rawBody` must be the exact bytes of the incoming request body, before
any JSON parsing or re-serialisation. With Express, this means
mounting the raw body parser BEFORE `express.json()`:

```ts
import express from 'express';
const app = express();
app.use('/sbs-callback', express.raw({ type: 'application/json' }));
// then handleSbsCallback uses req.body as a Buffer
```

Any whitespace change (a framework re-serialising the JSON) breaks
the body-hash and the signature.

## Dual ESM + CJS

The package ships both module systems. Both of these work from a
sandbox test script:

```ts
// ESM
import { verifyWebhookSignature } from '@sbs/webhooks-helper';

// CommonJS
const { verifyWebhookSignature } = require('@sbs/webhooks-helper');
```

The `package.json` `exports` field uses conditional exports in the
order `types` → `import` → `require` (Node.js's resolution algorithm
requires this exact order).

## Build

```bash
npm install
npm run build
```

Produces `dist/cjs/`, `dist/esm/`, and `dist/types/`. The
post-build scripts (`scripts/rename-*.js`) write the per-directory
`package.json` markers and rename the ESM `.js` files to `.mjs`.

## Tests

```bash
npm test
```

Same matrix as the Python helper: round-trip, tampered body, tampered
signature, wrong method, wrong institution_id, expired and future
timestamps, malformed timestamp, wrong key id, missing prefix, and a
clock-pinned reproducibility test.

## Installation

Distributed exclusively via the standards pack tarball at v0.1. Drop
`sdk-helpers/typescript/src/` into your project, or install from the
unpacked tarball. npm publication is deferred to v0.2 per ADR 0038.

## Verified compatibility

This helper round-trips against the same canonical-request shape the
SBS API uses to sign outbound webhooks. Cross-helper agreement with
the Python helper (and therefore with the server) is verified in CI.
