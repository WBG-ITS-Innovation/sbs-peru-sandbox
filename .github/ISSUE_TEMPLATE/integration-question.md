---
name: Integration question
about: You are deploying, integrating with, or reusing this reference implementation and something is unclear.
title: "question: <one-line summary>"
labels: ["question", "integration"]
---

## What you are trying to do

One paragraph, plain language. The outcome you want, not the command that
failed.

## Which surface

- [ ] Institution-facing API — submitting complaints (Tier 1) or batches (Tier 2)
- [ ] Internal API — the cockpit's server-side channel
- [ ] Supervisor cockpit (Next.js app)
- [ ] Agent layer / model providers
- [ ] Deployment, configuration, or operations
- [ ] Standards pack / OpenAPI contract / SDK helpers
- [ ] Something else

## What you have already read

We keep the answers in a small number of places, and it helps to know which
ones did not cover your case:

- [ ] [README](../../README.md) — setup and the two API processes
- [ ] [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) — how the system works
- [ ] [docs/PRODUCTION.md](../../docs/PRODUCTION.md) — deployment guide
- [ ] [docs/OPERATOR-CHECKLIST.md](../../docs/OPERATOR-CHECKLIST.md) — go-live gates
- [ ] [docs/HANDOVER-NOTES.md](../../docs/HANDOVER-NOTES.md) — the sharp edges
- [ ] [docs/adr/](../../docs/adr/) — the decision records
- [ ] The OpenAPI contract at `api/openapi/sbs-api-v1.yaml`

## Your setup

- Branch / commit:
- Deployment shape (Docker Compose / k8s / other):
- Model provider (`on_prem` / `cloud` / `replay`):
- Are you running both API processes (`:8443` institution-facing and `:8000`
  internal)? Running only one is the most common cause of a
  broken-looking cockpit.

## What you observed

Commands run and output, or the request and response. Redact secrets and any
non-synthetic data before pasting.

## Is this a question, a gap, or a bug?

- [ ] Question — I need to understand something
- [ ] Documentation gap — the answer exists but was not findable
- [ ] Possible bug — if so, the [bug template](bug.md) may fit better
- [ ] Missing capability — the [feature template](feature.md) may fit better

---

Please do not include production data, real complainant information, or
credentials. This repository is synthetic-data only. For a suspected
vulnerability, do **not** open an issue — follow [SECURITY.md](../../SECURITY.md).
