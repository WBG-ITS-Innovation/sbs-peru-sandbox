# `sbs-webhooks-helper` — Python webhook verification

Hand-maintained webhook signature verification for the SBS SupTech
Complaints API. **Pure Python standard library** — no external
dependencies. Installs anywhere Python 3.10+ runs, including locked-
down COOPAC environments that lack a C toolchain.

See [ADR 0038](../../docs/adr/0038-sdk-helper-scope-and-distribution.md)
for the design rationale and [ADR 0035](../../docs/adr/0035-outbound-webhook-signing-contract.md)
for the canonical-request contract this helper implements.

## What it does

Verifies the `X-SBS-Signature`, `X-SBS-Timestamp`, and `X-SBS-Key-Id`
headers attached to outbound webhook callbacks from the SBS sandbox.
On success, returns `None`. On failure, raises one of:

- `SignatureExpiredError` — timestamp outside the ±5-minute clock-skew
  window.
- `KeyIdUnknownError` — `X-SBS-Key-Id` is not `sandbox-v1`.
- `SignatureInvalidError` — HMAC SHA-256 over the canonical request
  did not match.

## What it does NOT do

This helper is intentionally tiny. It is **not** a full client SDK; it
does not generate API clients, handle OAuth tokens, manage mTLS
certificates, or implement replay protection (replay is the receiver's
responsibility — track recently-seen `(timestamp, signature)` pairs
within the skew window).

For client-code generation in Java / C# / Go, see the OpenAPI
Generator recipes in `standards-pack/recipes/`.

## Usage

```python
from sbs_webhooks import (
    KeyIdUnknownError,
    SignatureExpiredError,
    SignatureInvalidError,
    verify_signature,
)

YOUR_OUTBOUND_SECRET = b"..."     # bytes — distributed at onboarding
YOUR_INSTITUTION_ID = "SBS-001234"

def receive_callback(request):
    """Webhook callback handler — verify and process."""
    try:
        verify_signature(
            secret=YOUR_OUTBOUND_SECRET,
            key_id=request.headers["X-SBS-Key-Id"],
            timestamp=request.headers["X-SBS-Timestamp"],
            raw_body=request.body,         # bytes, EXACT bytes received
            signature_header=request.headers["X-SBS-Signature"],
            method=request.method,         # "POST"
            callback_path=request.path,    # "/sbs-callback"
            institution_id=YOUR_INSTITUTION_ID,
        )
    except (SignatureExpiredError, SignatureInvalidError, KeyIdUnknownError):
        return reject(401)
    # Signature good — process the payload.
    process(request.body)
    return ok(200)
```

Critical: pass `raw_body` as the **exact bytes** of the incoming
request body, before any JSON parsing. Any whitespace change (the
framework re-serialising the JSON) breaks the body-hash and the
signature.

## Installation

Distributed exclusively via the standards pack tarball at v0.1. Drop
`sbs_webhooks.py` into your project's Python path, or install from
the bundled source distribution:

```bash
pip install ./sdk-helpers/python/
```

PyPI publication is deferred to v0.2 per ADR 0038. The standards pack
is the v0.1 distribution surface.

## Tests

```bash
cd sdk-helpers/python/
python -m pytest tests/ -v
```

All tests run against pure stdlib — no fixtures require network,
docker, or a database.

## Verified compatibility

This helper round-trips against the same canonical-request shape the
SBS API uses to sign outbound webhooks. The CI test
`tests/test_python_helper_against_server_signer.py` (under the root
repo's `tests/` directory) imports both this helper and the server's
`api/sbs_api/webhook/signing.py` and verifies they agree byte-for-byte
on every test case.
