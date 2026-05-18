# CLAUDE.md — Working Agreement for the SBS SupTech Prototype

This file is the contract between the maintainer (Othman) and any Claude session working in this repo. Read it before doing anything else. If you find yourself acting against this file, stop and re-read.

This is a regulator-grade reference implementation, not a demo. Final audience: SBS Peru (Mariela, Sergio, Veronica), and a vendor who will inherit the code. Build for them.

---

## Six north-star principles

Every change must serve these. If a change violates one, raise it before writing code.

1. **One-command deploy.** `helm install` on a fresh cluster produces a working system. No undocumented steps. A fresh contributor on a fresh laptop must reach the running stack from `README.md` alone. If a step lives only in your head, it does not exist.

2. **Configuration over code.** The same container image deploys to dev, staging, prod, and SBS by changing config — taxonomy YAML, secrets, environment, Helm values. Never branch by environment in code. Never hard-code a regulator-specific value.

3. **Observability as a first-class feature.** Every service emits structured logs (JSON, with correlation IDs), Prometheus metrics, and OpenTelemetry traces from its first commit. If a feature ships without telemetry it is incomplete. Observability is not a Part 9 task — it is in every Part.

4. **Standards over inventions; onboarding is part of the product.** Required standards: OpenAPI 3.1, RFC 9457 problem+json, OAuth 2.0 client_credentials, mTLS, OCI images, Helm 3, SemVer, Conventional Commits, SLSA provenance, CycloneDX SBOM. Institutions get a documentation portal, a sandbox (the word "sandbox" — never "pilot bank"), generated SDKs for .NET, Java, Python, TypeScript via `openapi-generator`, a conformance test suite, and Postman/Bruno collections. If a problem has a published standard, use it; deviation requires an ADR.

5. **Plain-language explainability.** Every architectural artifact has a parallel plain-language version readable by Mariela (supervisor), Sergio (compliance lead), and Veronica (executive). No jargon without a glossary entry. No AI-sounding phrasing ("leverage", "delve", "unlock", "robust", "seamless", "cutting-edge"). Write like a calm, senior engineer briefing a regulator.

6. **Built on benchmarked precedent, not invention.** Every major design decision cites a comparator from a research file under [docs/research/](docs/research/) — regulator-domain (CFPB, FCA, BCB, EBA, ECB, HMRC, BIS, World Bank, CGAP) lives in [market-comparators.md](docs/research/market-comparators.md); supply-chain (Yelp `detect-secrets`, CISA, OpenSSF, 12-factor, public-sector OSS orgs) lives in [supply-chain-precedents.md](docs/research/supply-chain-precedents.md). Each ADR has a "Precedent" section naming the comparator(s) and a "Divergence" section explaining where SBS departs and why. The `benchmark-checker` subagent enforces this — the rule is *specificity of section and comparator*, not filename.

---

## Where things live

Read these before acting. They are authoritative; this file is a pointer index.

> **Model-call governance.** All LLM calls made by this project's tooling go through Azure OpenAI in the WBG ITS tenancy (four `AZURE_OPENAI_*` env vars; see [.env.example](.env.example)). Personal openai.com keys are not supported. This is a WBG data-governance requirement, not a preference.

- [docs/PLAN.md](docs/PLAN.md) — build plan, Parts 1–11, exit criteria. The roadmap.
- [docs/DECISIONS.md](docs/DECISIONS.md) — one-line decision log. Append on every non-trivial call.
- [docs/adr/README.md](docs/adr/README.md) — ADR index. Status: Proposed / Accepted / Superseded.
- [docs/adr/](docs/adr/) — individual ADRs (0001+).
- [docs/research/market-comparators.md](docs/research/market-comparators.md) — comparator research. Cite this in every design.
- [docs/research/README.md](docs/research/README.md) — index mapping comparators to PLAN.md sections.
- [docs/sessions/](docs/sessions/) — post-prompt session journals. One per closed prompt.
- [docs/sessions/_template.md](docs/sessions/_template.md) — journal format.
- [docs/sprint-input-log.md](docs/sprint-input-log.md) — running log of inputs from the Peru sprint.
- [docs/reviews/](docs/reviews/) — cross-model and adversarial review outputs.
- [docs/prompts/second-opinion-templates.md](docs/prompts/second-opinion-templates.md) — second-opinion prompt templates.
- [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) — workflow walkthrough and branch conventions.
- [docs/DEPLOY.md](docs/DEPLOY.md) — deployment guide (TOC scaffold until Part 9).
- [SECURITY.md](SECURITY.md) — disclosure path, sensitive-data rules, supported branches.
- [docs/setup/corporate-proxy-and-zscaler.md](docs/setup/corporate-proxy-and-zscaler.md) — WBG networking / CA bundle setup (DRAFT).
- [docs/setup/uv-quickstart.md](docs/setup/uv-quickstart.md) — uv install paths, the four commands, workspace layout, Zscaler caveats.
- [api/openapi/sbs-api-v1.yaml](api/openapi/sbs-api-v1.yaml) — canonical OpenAPI 3.1 contract (`bash scripts/serve-devportal.sh` renders it locally via Stoplight Elements). See [ADR 0027](docs/adr/0027-openapi-as-canonical-contract.md).
- [scripts/run-api.sh](scripts/run-api.sh) — run the FastAPI service locally. Three-command loop: `bash scripts/dev-up.sh` (Postgres + migrations), `bash scripts/run-api.sh` (API on :8000), `bash scripts/smoke-test.sh` (behavioral assertions). See [ADR 0028](docs/adr/0028-fastapi-application-structure.md).

---

## Workflow

### Slash commands (in `.claude/commands/`)

- `/part-start <N>` — open a Part. Returns goals, prerequisites from prior Parts, open second-opinion items, ready-to-proceed question.
- `/part-review <N>` — run subagent reviews against a Part's exit criteria.
- `/cross-review <file>` — send `<file>` to Azure OpenAI (via WBG ITS tenancy; deployment from `AZURE_OPENAI_DEPLOYMENT`) for an independent critique. Output lands in [docs/reviews/](docs/reviews/) with five required sections including a Triage line.
- `/second-opinion <file>` — run the adversarial `second-opinion` subagent.
- `/benchmark-check <file>` — verify the file cites a specific section of [docs/research/market-comparators.md](docs/research/market-comparators.md).
- `/decision-log <text>` — append a dated line to [docs/DECISIONS.md](docs/DECISIONS.md).
- `/adr-new <slug>` — scaffold a new ADR with Precedent + Divergence sections required.
- `/close-prompt` — closeout pipeline (see below). The keystone command.

### Subagents (in `.claude/agents/`)

- `reviewer` — general code review against PLAN.md and ADRs.
- `architect-guard` — refuses changes that contradict a locked decision unless an ADR amendment is in the same PR.
- `doc-sync` — catches code-doc drift.
- `regulator-readability` — gates anything Veronica or Sergio will see. Flags AI-sounding phrasing, jargon, latency-as-benchmark errors, "pilot bank" language, "real-time" instead of "near-real-time".
- `second-opinion` — deliberately adversarial. Surfaces at least one concrete weakness per design.
- `benchmark-checker` — verifies design changes cite a comparator from the research document.

### The closeout pipeline (`/close-prompt`)

Order is fixed. Each step blocks the next.

1. Six subagent reviews on the staged diff.
2. Cross-model review via Azure OpenAI (WBG ITS tenancy) → [docs/reviews/](docs/reviews/).
3. Adversarial review via the `second-opinion` subagent.
4. Fresh-machine deploy test (only if the prompt touches deploy or infra).
5. **Typed approval gate.** The script prints the summary and waits for the operator to type a literal approval string. There is no `-y` flag. If unattended, it exits non-zero.
6. Write the session journal to [docs/sessions/](docs/sessions/).
7. Auto-commit on a feature branch `part-NN/<slug>` with a Conventional Commits message generated from the staged diff.
8. Signed push (or warn and push unsigned if gitsign is not yet configured — Part 2 finalizes signing).
9. Open a PR via `gh pr create`, populating [.github/pull_request_template.md](.github/pull_request_template.md).

Main is protected. Nothing reaches main except by a human merging the PR after CI passes. Auto-merge to main is never enabled.

---

## Branch and commit conventions

- Branch names: `part-NN/<slug>` (e.g. `part-01/workflow-harness`). The pre-push hook at `.git/hooks/pre-push` rejects anything else.
- Commits: Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`).
- Signed commits via gitsign when Part 2 lands; until then, unsigned with a warning is acceptable.
- One PR per closed prompt. PRs reference the ADRs and PLAN sections they touch.

---

## Working principles

These are drawn from prior sessions and the maintainer's standing preferences. Treat each as a hard rule unless explicitly told otherwise.

- **Precision on scope.** When asked for a list of things, return only those things. Do not add features, refactor neighbouring code, or "improve" what was not asked for.
- **Plain language by default.** Write so Veronica or Sergio could read the same paragraph as a senior engineer. Glossary on first use of any acronym.
- **No AI-sounding phrasing.** Strike: leverage, delve, unlock, robust, seamless, cutting-edge, in today's fast-paced world, navigate the landscape, paradigm, ecosystem (as a metaphor), comprehensive (when "complete" works), utilize (when "use" works). Write like a person.
- **Governance flags.** When a decision touches policy (data residency, retention, approval thresholds, who-may-approve), flag it explicitly. Do not silently encode a policy assumption.
- **"Near-real-time", not "real-time".** Tier 1 ingestion is near-real-time. Saying "real-time" misleads the regulator about latency guarantees.
- **"Sandbox", not "pilot bank".** The integration environment is a sandbox. "Pilot bank" implies a chosen institution with privileged status, which we are not promising.
- **Weeks, not developer-days.** Plan in calendar weeks for a solo developer. Developer-days are an estimation antipattern in this context.
- **Illustrative metrics are flagged as such.** Any number in a doc that is not a measured value is labelled "illustrative" or "target", never presented as observed.
- **No invented benchmarks.** If we cite latency, throughput, accuracy — it is either measured (with the method) or labelled illustrative.
- **Read before writing.** Before editing a file, read it. Before contradicting a decision, find it in DECISIONS.md or the ADRs.
- **Small, reviewable commits.** A PR a reviewer cannot read in 20 minutes is too big.

---

## What this file is not

- Not a substitute for the PLAN or ADRs. If those contradict this file, those win and this file should be updated.
- Not a junk drawer. Hard cap: 350 lines. New material goes in a pointer, not inline.
- Not the source of truth on Part details — PLAN.md is.

---

## When a Claude session starts

1. Read this file.
2. Open [docs/PLAN.md](docs/PLAN.md). Identify the current Part.
3. Open [docs/sessions/](docs/sessions/) latest journal. Identify what was locked / deferred / flagged at the end of the previous session.
4. Run `/part-start <N>` if starting a new Part.
5. Work in small commits. Run `/close-prompt` at the end. Do not push to main.
