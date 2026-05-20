# ADR 0038 — SDK helper scope and distribution

- **Status:** Accepted
- **Date:** 2026-05-20
- **Target prompt / Part:** Prompt 9 / Part 7
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

ADR 0035 ships outbound webhook signing. The institutions receiving
those callbacks must verify the signature on their receiver side.
The signature primitive is HMAC SHA-256 over a five-line canonical
request, identical to the inbound shape from the ADR 0027
amendment. The primitive is straightforward; the failure mode is
the canonical-request construction — off-by-one newlines, trailing
whitespace handling, body-hash encoding (lowercase hex vs uppercase),
header-case sensitivity. The Open Banking UK implementer community
has documented this verification-failure pattern at length:
"translate the Python example to Java by eye" produces subtly wrong
implementations at depressing rates.

The institutional audience spans languages: Python and TypeScript
dominate at COOPACs and modern-stack banks; Java and Go are the
established server-side languages at legacy banks; C# / .NET
appears at a smaller cohort. A full hand-maintained client SDK in
every language is a permanent maintenance burden that this
prototype cannot sustain; "publish nothing and tell institutions to
write their own" is the failure-prone path the Open Banking UK
forums document.

The framing question is: where on the spectrum from "publish full
SDKs in every language" to "publish only the spec and an English
description" does the SBS sandbox sit, and what is the distribution
mechanism for whatever the answer is.

A second question is: does the Python helper depend on
the `cryptography` package (which requires a C toolchain to
compile its extensions) or pure stdlib? COOPACs run on locked-down
environments where C-toolchain availability is not guaranteed.

A third question is: does the TypeScript helper ship as ESM-only
(modern, clean), CJS-only (compatible with legacy institutional
Node.js setups), or dual ESM + CJS (covers both at the cost of a
slightly more complex build).

## Decision

1. **Two hand-maintained helpers covering exactly webhook signature
   verification.** Python at `sdk-helpers/python/sbs_webhooks.py`,
   TypeScript at `sdk-helpers/typescript/verifyWebhookSignature.ts`.
   Each is ~150 lines. Each exposes the same surface:
   `verify_signature` (raises on failure), `canonicalize_request`,
   `compute_signature`, `constant_time_compare`. Neither is a full
   client SDK; both are intentionally tiny.

2. **Python helper is pure stdlib — no `cryptography` dependency.**
   The helper uses `hmac`, `hashlib`, and `secrets` from the
   standard library. The HMAC SHA-256 + constant-time compare
   surface is fully covered by stdlib; there is no benefit to
   `cryptography` and a real cost in C-toolchain availability at
   the integrator side. The package's `pyproject.toml` declares
   `dependencies = []`.

3. **TypeScript helper ships dual ESM + CJS.** The `package.json`
   `exports` field uses conditional exports in the order
   `types` → `import` → `require` (Node.js's resolution algorithm
   requires this order). Two tsconfig files build the two
   variants: `tsconfig.cjs.json` (CommonJS, `dist/cjs/`) and
   `tsconfig.esm.json` (ESM, `dist/esm/`). Both
   `import { verifyWebhookSignature } from '@sbs/webhooks-helper'`
   and `const { verifyWebhookSignature } = require('@sbs/webhooks-
   helper')` work.

4. **Java and Go get reference verification snippets, not full
   helpers.** Two markdown files at `standards-pack/recipes/`
   (`webhook-verification-java.md`, `webhook-verification-go.md`)
   each contain a ~30-line working snippet that verifies a webhook
   signature. The snippets are tested in CI against a fixture
   signed payload; the tests are red if the snippets are wrong.
   Integrators adapt the snippet to their host language rather
   than translating Python by eye — which closes the dominant
   verification-failure mode.

5. **OpenAPI Generator recipes for the long-tail client-code
   problem.** Three markdown recipes at `standards-pack/recipes/`
   (`openapi-generator-java.md`, `openapi-generator-csharp-
   netcore.md`, `openapi-generator-go.md`). Each pins
   `openapitools/openapi-generator-cli:v7.10.0` and documents the
   "wrap, never edit generated files" pattern. Each recipe is
   smoke-tested in CI by invoking openapi-generator-cli against
   the published spec and asserting the expected source files
   are produced. `.NET` is dropped from the original list because
   the `csharp` and `csharp-netcore` generators differ materially
   and this prompt ships the modern `csharp-netcore` only.

6. **Helpers are distributed exclusively via the standards pack
   tarball at sprint kickoff.** PyPI / npm publication is deferred
   to a post-sprint release. The conservative ordering is in-repo
   first, GitHub release (via the standards pack) second, public
   registry once v1.0 stabilises.

## Precedent

[docs/research/market-comparators.md §5.A.S](../research/market-comparators.md#5as-sdk-helper-distribution-practice-added-prompt-9-for-adr-0038)
is the load-bearing reference.

The convergent Stripe pattern is "start narrow, expand based on
demand signal" — Stripe began with Python, Ruby, Node.js and added
PHP, Go, Java, .NET as its institutional customer base grew. The
expansion was data-driven, not aspirational. SBS's first cohort
(Diego's compliance officers + Patricia's operations managers +
Roberto's COOPAC risk officers) is Python-and-TypeScript-heavy;
the narrow starting point matches the documented audience without
prejudging language expansion.

OpenAPI Generator for the long tail is the regulator-domain default
— Open Banking UK, Brazil Open Finance, Berlin Group PSD2, and
Australian CDR all publish OpenAPI Generator recipes for languages
they do not first-class. The "wrap, never edit generated files"
pattern is the documented community consensus; editing generated
code produces unmergeable diffs on regeneration.

The reference verification snippet (Java, Go) shape follows Open
Banking UK's published Java snippet pattern: a tested ~30-line
function that integrators adapt to their host language.

## Divergence

We diverge from a uniform "publish in 7 languages" Stripe-mature
posture. The maintenance cost is real and the audience signal does
not yet justify it. The post-sprint review point is when SBS's
sandbox integration logs show language demand; at that point the
helper-set expands with data.

We diverge from "publish to PyPI / npm at v0.1". The supply-chain
responsibility (CVE response, deprecation policy, attestation
chain) is incurred from the first published version; this is a
v1.0 commitment, not a v0.1 commitment. Tarball-via-GitHub-release
is the v0.1 distribution surface.

We diverge from depending on `cryptography` in the Python helper.
The COOPAC C-toolchain-availability constraint is the load-bearing
reason; the HMAC surface is small enough that stdlib coverage is
complete. The same posture would not apply to a helper that needed
elliptic-curve operations (HSM-backed signing, mTLS cert handling)
where stdlib is insufficient and `cryptography` is unavoidable.

We diverge from ESM-only TypeScript. Many institutional Node.js
environments still run CommonJS; dual exports avoid the adoption-
friction trap. The cost is the two-tsconfig build setup, which is
a documented one-time cost.

We diverge from a full hand-written Java or Go helper. The
verification snippet plus the OpenAPI Generator recipe together
cover the use case without taking on permanent maintenance burden
in languages whose audience demand has not been demonstrated.

## Consequences

- Institutions in Java, csharp-netcore, and Go invoke OpenAPI
  Generator themselves using the published recipe. Generated code
  is wrapped, never edited; the recipe makes this explicit.

- Institutions in any language adapt the published verification
  snippet (or one of the helpers) to their canonical-request
  construction code. The fixture-signed-payload CI test makes the
  snippets known-correct.

- The Python helper installs anywhere Python 3.10+ runs. No C
  toolchain required. Supply-chain surface is just the standard
  library.

- The TypeScript helper installs in both CJS and ESM Node.js
  environments. The dual-export `package.json` shape is the
  documented modern pattern.

- v0.2 (the post-sprint release with conformance suite and Bruno
  collections) is the natural decision point to (a) add languages
  to the first-class helper set if demand signal justifies it,
  and (b) publish to PyPI / npm if the v1.0 commitment is ready.

- The Java and Go verification snippets are non-droppable at the
  hour-7 gate in the closeout discipline. Dropping them would
  re-introduce the "translate by eye" failure mode the snippets
  are designed to prevent.
