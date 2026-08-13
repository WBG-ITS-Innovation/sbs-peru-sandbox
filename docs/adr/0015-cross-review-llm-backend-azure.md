# ADR 0015 — LLM backend for development: Azure OpenAI under WBG tenancy

- **Status:** Accepted
- **Date:** 2026-05-16 (decided in practice), 2026-08-13 (written, and extended to the agent runtime)
- **Target prompt / Part:** Prompt 1.5 / Part 2 (cross-review tooling); extended in Part 12 (agent layer)
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer, under WBG ITS data-governance policy.

## Context

This ADR was indexed as `Proposed` from Prompt 1.5 and cited as settled by
[ADR 0020 §3](0020-env-handling-policy.md) ("the four `AZURE_OPENAI_*`
variables … see ADR 0015 for the Azure OpenAI backend decision") but the file
was never written. The decision it describes has been in force since the first
commit that read `AZURE_OPENAI_API_KEY`: `.env.example` documents the
four-variable shape, `scripts/assistant_query.py` calls Azure directly, and CI
stores the same four secrets. Writing it now closes a dangling reference rather
than making a new choice.

Two things did change and are recorded here:

1. The same credentials now back a **second** consumer. Until this ADR was
   written, Azure OpenAI served only developer-side tooling (cross-review,
   the demo assistant). The agent runtime's `CloudProvider` was a scaffold
   that raised `NotImplementedError`. It is now implemented against these
   same four variables — see [ADR 0001 §Amendment
   2026-08-13](0001-three-layer-mcp-a2a-langgraph.md).
2. The **boundary** that keeps this defensible had to be stated explicitly,
   because a working cloud provider can carry supervisory content off-tenant
   in a way a raising scaffold could not.

## Decision

### D1 — Azure OpenAI under WBG tenancy; never personal openai.com keys

All model calls from this repository that are not served on-prem go through
WBG-tenanted Azure OpenAI, configured by exactly four variables under their
bare, un-prefixed names:

| Variable | Meaning |
| --- | --- |
| `AZURE_OPENAI_API_KEY` | Resource key. Never logged, never in an exception message. |
| `AZURE_OPENAI_ENDPOINT` | `https://<resource>.openai.azure.com/` |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment name — Azure routes on this, not the base model name. |
| `AZURE_OPENAI_API_VERSION` | REST API version; must support the `tools` parameter. |

The names stay un-prefixed even though every other setting in `Settings`
carries `SBS_API_`: they are the shape WBG ITS hands out and the shape CI
secrets already use, and renaming them in the application would mean
maintaining a translation for no gain. `Settings` reads them through an
explicit `validation_alias`, which bypasses the `env_prefix` while keeping
configuration to one seam (`api/sbs_api/config.py`).

Personal `openai.com` keys are rejected, not merely discouraged:
`scripts/cross_review.py` refuses them.

### D2 — The cloud path is for development against synthetic data

`SBS_API_MODEL_PROVIDER=cloud` requires `SBS_API_CLOUD_LEGAL_APPROVED=true`.
Setting that flag is an **operator assertion** of development use with
synthetic data only, pending legal sign-off on PII isolation and data
residency. It is not the sign-off. Nothing in the codebase can verify the
assertion, which is exactly why it is a deliberate, documented act rather
than a default.

Supervisory-grade narratives stay on the on-prem path. The prototype's
corpus is synthetic by construction (ADR 0036) and PII is redacted before any
agent sees a narrative (ADR 0044), so the cloud path in development moves
synthetic text with redacted derivations — but the joined feature shape still
carries supervisory judgement, which is why the gate exists at all.

### D3 — One interface, so the on-prem path is a configuration change

`CloudProvider` and `OnPremProvider` implement the same `ModelProvider`
protocol and the same native tool-calling contract. Moving the SBS
workstation from cloud to on-prem is `SBS_API_MODEL_PROVIDER=on_prem` plus a
vLLM endpoint — no agent code changes. `on_prem` remains the default so that
an unconfigured host cannot silently reach off-tenant.

### D4 — Corporate TLS interception is configuration, not a code path

On the WBG network the Azure endpoint is presented by
`pa-wbg-decrypt.worldbank.org`, issued by `WBG Cloud Root CA`, which the
`certifi` bundle does not carry; unset, this fails with
`CERTIFICATE_VERIFY_FAILED`. `SBS_API_CLOUD_CA_BUNDLE` points httpx at a
bundle that includes the corporate root. It is empty by default, so a host
off that network needs no configuration, and no corporate certificate is
committed to the repository.

## Consequences

- Developer onboarding needs four values from WBG ITS before the cloud path
  or the cross-review tooling works; nothing else in the stack requires them.
- Key rotation is a WBG ITS operation. The application holds the key only in
  memory and redacts it from all output, so rotation is a `.env` edit plus a
  restart.
- A second consumer of the same key means a leak now exposes the agent path
  too. The mitigation is unchanged (rotate first, then expunge — ADR 0020 §5)
  but the blast radius is larger, and `SECURITY.md` says so.
- Azure deployments disagree about request-parameter dialects
  (`max_completion_tokens` vs `max_tokens`, whether `temperature` may be
  set). `CloudProvider` adapts at runtime on the 400 rather than pinning a
  dialect, which costs at most one wasted request per process.

## Precedent

See [docs/research/market-comparators.md §5.E — "On-prem / sovereign agentic
layer"](../research/market-comparators.md#5e-on-prem--sovereign-agentic-layer).
The section records that the on-prem constraint follows from data-privacy,
data-localization, and vendor-dependency concerns in supervisory AI, and that
vLLM's value as the local serving layer is precisely its OpenAI-compatible
API and tool-calling surface. Both halves of this ADR follow from that: the
cloud backend is development-time convenience behind an explicit gate, and it
is worth implementing against the *same* OpenAI-shaped tool-calling contract
so that the sovereign path is a configuration change rather than a rewrite.

For the credential-handling posture, see
[docs/research/supply-chain-precedents.md §5 — "Environment-variable / secret
handling"](../research/supply-chain-precedents.md#5-environment-variable--secret-handling),
which names this repository's contribution as "per-tool wiring (Azure OpenAI
four-variable shape, WBG ITS tenancy), not a new posture" — 12-factor config
III, GitHub encrypted secrets in CI, and the CFPB / FCA / HMRC public-sector
application of the same pattern.

## Divergence

Comparators in §5.E describe a sovereign, on-prem serving layer as the
end state for supervisory AI, and this ADR admits a hosted backend. The
divergence is bounded three ways: the default provider is on-prem, the cloud
path needs an explicit opt-in flag that names what it is asserting, and the
tenancy is the institution's own (WBG) rather than a personal or
vendor-default account. What is not bounded by code — that the data really is
synthetic — is the operator's assertion, and is stated as such in
`.env.example` and in D2 above.
