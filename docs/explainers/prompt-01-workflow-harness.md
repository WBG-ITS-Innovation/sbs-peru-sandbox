# Prompt 1 Explainer — Workflow Harness, GitHub Standards, and Closeout Pipeline

**Repo:** WBG-ITS-Innovation/sbs-peru-sandbox
**Merged commit:** 6382a32a8041a0996ec425564e4ecd6e72352356
**Date:** 2026-05-15 / 2026-05-16
**Status:** Merged to main

---

## What this document is

This is the plain-language explainer for Prompt 1. It covers what was built, why we built each piece, every technical term we used, how the pieces fit together, and what each component does in practice. It's written for someone who isn't a software engineer — Mariela, Sergio, Veronica, Fisnik — but who needs to understand the foundation of the project to review it, sign off on it, or join the work.

If you're a software engineer reading this, you'll find some parts obvious. Skim those. The depth is for the non-engineer audience.

Read this end-to-end once, then keep it as a reference. Future Prompt explainers (Prompts 2–30+) will assume you've read this one.

---

## The one-paragraph summary

We built a development workflow system — the "harness" — that makes every subsequent piece of work on this project produce regulator-grade output by default. The harness has five layers: a project constitution (CLAUDE.md), six specialized AI subagents that review every change, eight slash commands that automate repeatable workflows, a cross-model review pipeline that validates Claude's work against a second model (Azure OpenAI through WBG), and a closeout pipeline that handles git operations safely with an explicit human approval gate. We also wired GitHub to enforce standards (branch protection, PR templates, automated dependency updates), expanded the project plan to encode the full delivery commitment, and committed market research that anchors design decisions in benchmarked precedent rather than invention. The output of Prompt 1 is not a feature — it is the discipline that produces all features going forward.

---

## Why this matters before any product code is written

The SBS engagement has hard constraints that most software projects don't have:

- **Hard deadline.** July 2026, tied to a presidential transition. No room to slip.
- **Regulator-grade quality.** SBS will deploy this in production to ingest complaint data from 20–60 supervised institutions. Bugs aren't an inconvenience — they're a regulatory event.
- **On-premises deployment.** PII never leaves SBS's perimeter. Architecture has to be deployable to bare-metal or SBS's own Azure tenancy without modification.
- **Multiple reviewers with non-technical backgrounds.**
- **Audit trail is the deliverable.** Every decision must be traceable years later by people who weren't in the room.

Building this directly — writing API code, training models, deploying agents — without the discipline layer first is the failure mode that wrecks regulator projects. The discipline layer is harder to retrofit than to install upfront. So Prompt 1 installed it.

Think of it like building a skyscraper. You don't start with the lobby. You start with the foundation, the cranes, the construction protocols, the safety officer's checklist, the change-order process. The lobby is months away. But everything that goes into the lobby depends on the foundation work being right.

---

## Layer 1 — The project constitution (CLAUDE.md)

### What it is

A single markdown file at the root of the repository called `CLAUDE.md`. It's 128 lines long.

### What it does

Every time someone opens Claude Code in this repository, this file is automatically loaded into the AI's context. It tells the AI: "Here's what this project is, here are the rules, here are the standards, here's where to find more detail."

Without this file, every conversation with Claude Code would start cold. The AI would re-derive context from scratch, make slightly different choices each time, drift from established conventions. With this file, the AI is grounded in the project's actual standards from the first message.

### What's inside

Three sections.

**Top section — the six north-star principles.** These are the non-negotiable rules every change is judged against:

1. **One-command deploy.** Running `helm install` on a fresh Kubernetes cluster produces a working system. No undocumented steps, no "and then SSH in and...". Testable by a fresh contributor following only `docs/DEPLOY.md`.
2. **Configuration over code.** Every environment-specific value (endpoints, model names, retention policies) lives in declarative configuration files, not hardcoded. The same container image deploys to dev, staging, prod, and SBS by changing config.
3. **Observability as a first-class feature.** Every service emits structured logs, metrics, and traces from the first commit. Operators can see what the system is doing without asking the developers.
4. **Standards over inventions, and onboarding is part of the product.** We use OpenAPI 3.1, RFC 9457, OAuth 2.0, mTLS, and other industry standards instead of inventing our own. Institutions integrating with SBS get a developer portal, sandbox, generated SDKs, and a conformance test suite — not just a README.
5. **Plain-language explainability.** Every technical artifact has a parallel plain-language version. Mariela, Sergio, and Veronica can read what the system does without an engineer translating.
6. **Built on benchmarked precedent, not invention.** Every major design decision cites a comparator from `docs/research/market-comparators.md` (CFPB, FCA, BCB, EBA, ECB, HMRC, BIS, World Bank, CGAP). When we diverge from a precedent, an ADR explains why.

**Middle section — pointers.** Links to the other key documents: `PLAN.md` (the full plan), `DECISIONS.md` (decision log), `docs/adr/README.md` (ADR index), `docs/sessions/` (session journals), `docs/reviews/` (cross-review reports), `docs/sprint-input-log.md` (Peru sprint feedback log), `docs/research/market-comparators.md` (market research).

**Bottom section — working principles.** Drawn from earlier project conversations and corrections:
- Use "near-real-time" not "real-time" for the Tier 1 API.
- Describe effort in weeks, not developer-days.
- Flag latency numbers as targets/examples, not benchmarks.
- Use "sandbox" not "pilot bank."
- No AI-sounding phrasing.
- Decisions requiring SBS policy input (e.g., human-in-loop on critical actions) get flagged, not assumed.

### Why this works

Most teams have a `README.md` with project setup instructions. CLAUDE.md is something stronger: a *standards reference* loaded into the AI's working context for every interaction. It's how we make sure that someone using Claude Code in this repo, two months from now, after fifty intervening conversations, still gets output that respects the original standards.

---

## Layer 2 — Six specialized subagents

### What is a subagent

A subagent in Claude Code is a specialized AI reviewer. Each subagent is a markdown file in `.claude/agents/` that defines:

- The subagent's name
- Its purpose (what it reviews)
- Its rules (what to look for, what to flag, what to approve)
- Concrete examples of failures it should catch

When invoked, Claude Code spawns a fresh AI conversation with that markdown as the system prompt, in a restricted context. The subagent reads the diff or document it's reviewing, applies its rules, and produces a verdict: APPROVE, APPROVE WITH NITS, or BLOCK.

The same underlying model (Claude Opus 4.7) runs every subagent. The difference is in the instructions. A `reviewer` subagent doesn't try to be a `regulator-readability` subagent because its instructions are sharply different.

**Why specialized reviewers beat a general-purpose review pass:** focused attention catches things broad attention misses. A reviewer trying to check architecture, documentation, security, readability, and benchmarks all at once does a worse job of each than five reviewers each focused on one thing.

### The six subagents

**1. `reviewer`** — General code review. Checks that the diff matches the prompt's "Files affected" list, that there are no drive-by changes, that PLAN.md is honored, that ADRs are respected. This is the default reviewer for every change.

**2. `architect-guard`** — The most powerful subagent. Refuses to approve any change that contradicts a locked architectural decision (from PLAN.md's "Locked architectural decisions" block or an Accepted ADR) without an explicit ADR amendment in the same change. Prevents architectural drift over 30+ prompts. Example of what it catches: a PR that changes the API from REST to GraphQL without amending ADR 0003.

**3. `doc-sync`** — Catches code-documentation drift. If a code change implies a documentation change and the documentation isn't updated, this subagent flags it. Example: if PLAN.md says "five specialist agents" but the agent restructure absorbed those into other parts without updating PLAN.md, doc-sync catches it.

**4. `regulator-readability`** — Runs on documents Veronica, Sergio, and Mariela will read. Flags AI-sounding phrasing (words like "leverage", "robust", "seamless", "cutting-edge"), jargon without plain-language framing, latency-as-benchmark errors (using "real-time" when "near-real-time" is correct), pilot bank language (when "sandbox" is correct), and metric claims stated as facts when they should be flagged as illustrative examples.

**5. `second-opinion`** — Deliberately adversarial. Its job is to argue against the proposed approach, surface what the primary reviewer missed, and produce a structured critique with concrete weaknesses. Catches groupthink failures.

**6. `benchmark-checker`** — Verifies that significant design changes cite a benchmarked precedent from `docs/research/market-comparators.md`. If an ADR proposes a normalized complaint indicator without citing BCB's complaint ranking pattern, this subagent flags the gap. Prevents the "we invented this" failure mode when we should be citing CFPB or FCA or BCB.

### How subagents are invoked

Three ways:

1. **By a slash command.** When you run `/close-prompt`, it invokes all six subagents on the staged diff and aggregates their verdicts.
2. **By another subagent.** Some subagents chain to others — `reviewer` may invoke `architect-guard` when it sees architecture files.
3. **Directly.** You can ask Claude Code: "Run the regulator-readability subagent on docs/DEPLOY.md." It will.

The subagents do not run automatically. They run when invoked. That's intentional — review is a deliberate act, not background noise.

### A note on "are these real agents"

Yes. They are real. They are markdown files because that's how Claude Code's agent architecture works — configuration in plain text, version-controlled, reviewable in PRs, no hidden state. The "agent" is the combination of (a) the markdown system prompt and (b) the underlying model that executes it. Same pattern as how a Docker container is "just a tar file plus a config" — the boring representation hides genuine power.

To verify they exist, run `ls .claude/agents/` in your terminal. To verify they work, ask Claude Code to invoke one on a sample input.

---

## Layer 3 — Eight slash commands

### What is a slash command

A slash command is a custom workflow shortcut. Type `/<command-name>` in Claude Code and it executes a predefined sequence of actions. Each command is a markdown file in `.claude/commands/` that defines what the command does.

Slash commands replace multi-step manual processes with single typed commands. Same pattern as keyboard shortcuts — they exist so repeatable work doesn't have to be repeatedly described.

### The eight commands

**1. `/part-start <N>`** — Begins work on Part N of the plan. Reads PLAN.md for that Part's goals, lists prerequisites from earlier Parts, surfaces any open second-opinion items or deferred ADRs, and asks "ready to proceed?" Stops you from blindly starting work without context.

**2. `/part-review`** — Runs all six subagents on the current staged diff, aggregates verdicts, and reports. Used during work, not just at closeout.

**3. `/cross-review <target>`** — Calls a second AI model (Azure OpenAI, gpt-5 deployment) through the WBG tenancy with a structured critique prompt. Writes the critique to `docs/reviews/YYYY-MM-DD-<slug>.md` with five sections: Summary, Disagreements with primary review, Risks not flagged elsewhere, Recommended actions, Triage. The cross-review catches what one model misses by virtue of being a different model.

**4. `/second-opinion <target>`** — Invokes the adversarial `second-opinion` subagent on a specific file or design.

**5. `/benchmark-check <target>`** — Invokes the `benchmark-checker` subagent on a specific file (typically an ADR draft).

**6. `/decision-log <entry>`** — Appends a dated entry to `DECISIONS.md` with correct formatting. Used to record decisions made during a session that don't yet rise to ADR-level.

**7. `/adr-new <slug>`** — Creates a new ADR file from the template at `docs/adr/_template.md`, populated with the next available ADR number, ready for editing.

**8. `/close-prompt`** — The keystone command. See Layer 5 below.

### Why this matters

Without slash commands, every closeout would be a manual sequence: "OK now run the six subagents one by one, now call the cross-review script, now write the session journal, now commit, now push, now open the PR." That sequence is error-prone and easy to skip steps. With `/close-prompt`, the sequence is fixed, automated, and applied identically every time.

---

## Layer 4 — Cross-model review (Azure OpenAI through WBG)

### What it is

For every significant change, we run the work through a second AI model — not Claude — and surface any disagreements. The second model is GPT-5 (or whichever deployment is configured) running on Azure OpenAI in World Bank's Azure tenancy.

### Why this matters

Different AI models have different blind spots. Claude might miss something a GPT model would catch, and vice versa. Where the two models *disagree*, there's usually something real worth investigating — either Claude is wrong, GPT is wrong, or the design itself is genuinely ambiguous.

This pattern is called "cross-model validation" and it's increasingly standard in AI-assisted engineering. It costs cents per review and catches issues that would cost hours to find downstream.

### Why Azure OpenAI specifically (not personal OpenAI)

Two reasons:

**Data governance.** Azure OpenAI guarantees that prompts and outputs are not used for model training. Personal OpenAI accounts do not guarantee this by default. For a project handling regulator-related context (even synthetic data and architecture discussions), WBG governance requires Azure OpenAI.

**Architectural alignment.** SBS's likely production deployment is on their Azure tenancy. By using Azure OpenAI for cross-review, we're aligned with the production architecture rather than introducing a separate OpenAI dependency.

### How it works in practice

A Python script at `scripts/cross_review.py` reads a file or git diff, calls the Azure OpenAI API with a structured critique prompt, and writes the response to `docs/reviews/YYYY-MM-DD-<slug>.md`. The script requires four environment variables: `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`. Without all four, the script fails loudly rather than silently skipping.

The script is called as part of `/close-prompt`, but you can also call it directly: `python3 scripts/cross_review.py --target CLAUDE.md`.

### The audit trail

Every cross-review report is committed to git. Over time, `docs/reviews/` accumulates a record of every cross-model critique on every significant change. Someone can later audit: "What did the second model think about this design decision?" by reading the corresponding review file.

### One operational note for future contributors

When connected to the WBG VPN, the Zscaler corporate SSL inspection proxy intercepts outbound HTTPS calls. Python's default SSL trust store doesn't include the Zscaler root certificate, so `cross_review.py` will fail with a `CERTIFICATE_VERIFY_FAILED` error. Fixes (in order of preference): install `pip-system-certs` (bridges Python to the OS keychain), set `REQUESTS_CA_BUNDLE` to a manually-exported cert bundle, or disable VPN for the call (not recommended). This will be documented in `docs/CONTRIBUTING.md` in Prompt 2.

---

## Layer 5 — The closeout pipeline (`/close-prompt`)

### What it is

The keystone command. When invoked, it executes the full quality and audit pipeline for closing out a unit of work (typically a Prompt), then handles the git operations to deliver the work to a GitHub Pull Request.

### What it does, step by step

1. **Inventory.** Shows what files are staged, what Part this is, what branch will be created.
2. **Subagent reviews.** Runs all six subagents on the staged diff. Aggregates verdicts. Blocks if any subagent returns BLOCK.
3. **Cross-model review.** Calls `cross_review.py` on the staged diff. Writes the critique to `docs/reviews/`.
4. **Adversarial review.** Runs `second-opinion` on the staged diff specifically.
5. **Deploy test (when applicable).** If the change touches infrastructure files (Helm, Terraform, Docker), recommends running `scripts/fresh_machine_test.sh` on a clean environment. (Currently has a false-positive regex bug — fix coming in Prompt 2.)
6. **Closeout summary.** Prints: files staged, draft branch name, draft commit message, draft PR body. This is the last thing before the irreversible step.
7. **Typed approval gate.** Pauses and prompts: `approval>`. You must type `approve` (or `APPROVE`) to proceed. Any other input aborts the pipeline. This gate is intentionally not bypassable from non-interactive contexts — it requires a human at a keyboard, not a script.
8. **Session journal generation.** Writes a session journal entry to `docs/sessions/` summarizing the closeout.
9. **Branch creation.** Creates a feature branch named `part-NN/<slug>` (e.g., `part-01/workflow-harness`). Pre-push hook validates the name.
10. **Commit.** Generates a Conventional Commits-formatted message (e.g., `chore: workflow harness`). Signs the commit if `gitsign` is configured (coming in Prompt 2; currently warns and commits unsigned).
11. **Push.** Pushes the feature branch to GitHub.
12. **PR creation.** Calls `gh pr create` with the PR template populated.

### Why the typed approval gate is the most important line of defense

Without the gate, an automated pipeline could push broken code to GitHub. With the gate, you read the diff summary, the commit message, and the PR body, and *then* decide whether to proceed. The gate makes Claude Code unable to push code on its own — only you can authorize the push, and only after seeing exactly what will happen.

This is the difference between "AI-assisted development" and "AI runs your repo." We've chosen the first.

### Why feature branches and PRs (not direct push to main)

The closeout pipeline pushes to a feature branch, then opens a PR against `main`. It never pushes directly to `main`. This is enforced two ways: by the pipeline's design, and by GitHub branch protection on `main` (which would reject a direct push even if attempted).

**The benefits of this pattern:**

- Every change is reviewable as a discrete unit before it lands on `main`.
- Every change has a permanent PR record (title, description, commits, merge author, merge time).
- Every change can be reverted cleanly because of squash-merge.
- `main` is always deployable because every change passed the gate to reach it.

This pattern is called **GitHub Flow** (or "trunk-based development with PRs"). It's the standard at modern continuously-deployed systems — Stripe, GitHub itself, Vercel, Anthropic. The alternative — GitFlow with develop/release/staging branches — is heavier and made sense for shrink-wrapped software in the 2010s, not for continuously-deployed regulatory systems.

---

## Layer 6 — GitHub standards and governance

### What we configured on the GitHub side

**Branch protection on `main`.** Direct pushes to `main` are refused. Every change must go through a PR. Force-push is disabled. Deletion is disabled. Linear history is required. Conversation resolution is required before merging. (Required-approvals count is currently 0 for solo work; bump to 1 when a second human joins.)

**Pull request template** at `.github/pull_request_template.md`. Every new PR is pre-populated with sections: Summary, Linked ADR, North-star principles affected, Exit criteria progress, Test plan, Subagent verdicts. Reduces the chance of opening a PR with no context.

**CODEOWNERS** at `.github/CODEOWNERS`. Defines who must review which paths. Currently you're the only owner; commented placeholders for Antoine on `/infra/` and `/agents/`, Fisnik on `/docs/adr/`, ready to activate when those people join the repo.

**Issue templates** at `.github/ISSUE_TEMPLATE/`. Four templates: bug report, feature request, ADR request, second-opinion-needed. Makes work visible and trackable.

**Dependabot** at `.github/dependabot.yml`. Weekly automated dependency updates for Python (pip), Node (npm), GitHub Actions, and Docker. Each update opens a PR. Once CI is wired in Prompt 8, each PR automatically tests before being mergeable.

**SECURITY.md** at the repo root. Vulnerability disclosure policy. Standard for regulator-grade repositories.

**CODE_OF_CONDUCT.md** at the repo root. Standard Contributor Covenant 2.1, fetched canonically.

**LICENSE** placeholder. Pending legal review (Apache 2.0 is the target per DECISIONS.md; not yet locked).

**Pre-push hook** at `.git/hooks/pre-push` (installed by `scripts/setup_hooks.sh`). Enforces the `part-NN/<slug>` branch naming convention. A push of a misnamed branch like `foo-bar` is rejected.

### Why every one of these matters for a regulator project

A regulator-grade project has to answer specific questions when audited:

- *Who changed what, when, and why?* → Git history + PR records.
- *Was the change reviewed?* → PR approval record.
- *Did automated checks pass?* → CI status on the PR (once Prompt 8 lands CI).
- *Can the change be reverted cleanly?* → Squash-merge means one commit per change.
- *Was the dependency stack maintained?* → Dependabot's PR history.
- *Was there a security disclosure process?* → SECURITY.md.

Without these in place, the answers to those questions are "I think so" and "let me reconstruct it from memory." With them in place, the answers are URLs to specific, immutable, dated artifacts.

---

## Layer 7 — The audit trail

The audit trail is not a single thing — it's seven independent layers, each of which can be reconstructed independently of the others if any fails:

1. **Git commit history on `main`.** Every commit is immutable, cryptographically hashed, attributed to an author with a timestamp. Cannot be retroactively modified without breaking every subsequent hash.

2. **PR records on GitHub.** Every PR's title, description, commits, comments, approver, merger, and merge time is preserved permanently.

3. **Session journals** at `docs/sessions/`. One markdown file per prompt, summarizing what was done, what was decided, what's blocked. Written automatically by `/close-prompt` and committed to git.

4. **Decisions log** at `DECISIONS.md`. Append-only log of every meaningful decision made during the project. Entries added via `/decision-log`.

5. **ADRs** at `docs/adr/`. Architectural Decision Records — structured documents capturing significant architectural choices, with status (Proposed, Accepted, Superseded), context, decision, consequences, and alternatives considered. Currently 15 ADRs in the queue (0001–0015), all status "Proposed", to be written when their work begins.

6. **Cross-review reports** at `docs/reviews/`. One markdown file per cross-review, capturing what the second AI model thought about a given change.

7. **Sprint input log** at `docs/sprint-input-log.md`. Empty for now; ready to capture feedback from the Peru in-person sprint. Columns: Date, Source, Input, Disposition (Accepted → ADR / Deferred / Rejected with reason), ADR ref if applicable.

If any one of these layers is lost or corrupted, the others can reconstruct most of the history. That's defense-in-depth for audit.

---

## Layer 8 — Market research as a first-class artifact

### What we committed

A 10-section market research document at `docs/research/market-comparators.md` covering:

- US CFPB Consumer Complaint Database (closest reference for complaint data fields and API access)
- Banco Central do Brasil complaint ranking (LatAm precedent for normalized complaint indicators)
- UK FCA complaints reporting modernization (firm-submitted complaint reporting regime)
- Australia AFCA + ASIC IDR reporting (separation of consumer dispute resolution vs supervisor reporting)
- Mexico CONDUSEF systems (Spanish-language workflow comparator)
- Secondary comparators: Colombia SFC, Chile CMF, Bank of Spain, BaFin
- Two-tier reporting precedents: ECB IReF, ECB BIRD, EBA DPM/XBRL, HMRC Making Tax Digital bridging software
- Technical component map: API/schema, event-driven ingestion (Kafka/NATS/RabbitMQ), Spanish NLP (BETO, RoBERTa-BNE), explainability (XGBoost + SHAP), on-prem inference (vLLM, Mistral), agent orchestration (LangGraph, AutoGen, Semantic Kernel), dashboards (Apache Superset)
- Publications to cite: World Bank market-conduct SupTech, Cambridge State of SupTech 2025, BIS Working Paper 1309, BIS FSI Insights 73, IMF AI in Supervisory Authorities, World Bank/CEPR AI in EMDE supervision, BIS Project Ellipse, BIS Project Aurora
- Recommended positioning for the SBS final report

### Why this is a first-class artifact

The `benchmark-checker` subagent enforces that significant design changes cite this document. If an ADR proposes a normalized complaint indicator and doesn't cite BCB's complaint ranking pattern from section 2, the subagent flags it. This is what prevents the "we invented this" failure mode.

The cross-reference index at `docs/research/README.md` maps each comparator to specific PLAN.md sections so the subagent has concrete pointers to check against.

### Why market research isn't a one-time artifact

Regulator and SupTech publications land monthly. We'll periodically refresh this document via new research passes — not in Prompt 1, but as the project progresses. The document is structured for append-only revision so updates don't overwrite the original analysis.

---

## What got expanded in PLAN.md

The original plan had six Parts (Foundation, Data Model & API Skeleton, Ingestion Tier 1, Ingestion Tier 2 + Synthetic Data, ML Substrate, Agent Infrastructure). Prompt 1 added five more:

**Part 7 — Developer Portal + Onboarding Tier A.** Documentation portal, sandbox formalization, SDK generation for .NET/Java/Python/TypeScript via openapi-generator, conformance test suite, Postman/Bruno collections, "Getting started in 30 minutes" guide.

**Part 8 — Self-Service Onboarding + Per-Institution Ops (Tier B).** Self-service credential issuance portal, per-institution health dashboards, rate limit and quota visibility, integration support tooling.

**Part 9 — Production Readiness.** Helm chart finalization, Terraform modules for bare-metal and Azure tenancy targets, runbook, DR plan, k6 load testing, chaos testing basics, security audit checklist, SBS handoff package.

**Part 10 — AI/ML Evaluation Framework.** Golden sets per model, regression test harness, drift detection dashboards, prompt registry with versioning, extended model registry with eval results.

**Part 11 — Standards Pack & Reporting Taxonomy Distribution.** Machine-readable Anexo 1-A as a published artifact: JSON Schema, code lists, validation rules, OpenAPI, batch manifest, error catalogue, sample payloads, versioning policy. This is what supervised institutions integrate against.

Each Part has explicit exit criteria, not vague aspirations.

The PLAN restructure note at the top of PLAN.md honestly documents what changed: the original Parts 7–10 (Specialist Agents I/II, Frontend, Polish) were absorbed into the new structure, with their content to be reintroduced as extensions to Part 6 (Agent Infrastructure) when their work begins. This is itself an audit-trail decision.

---

## The 15-ADR queue

Architectural Decision Records (ADRs) are structured documents capturing significant architectural choices. Each ADR has a status (Proposed → Accepted → possibly later Superseded), a context (forces in play), a decision (what we chose), consequences (positive and negative), and alternatives considered.

The full ADR queue currently has 15 entries, all status "Proposed":

- **0001** — Three-layer agent architecture (MCP + A2A + LangGraph). Target: Prompt 9.
- **0002** — Deployment topology and PII boundary (bare-metal vs Azure tenancy, hybrid pattern, what crosses the boundary). Target: before Peru sprint.
- **0003** — API design principles and versioning policy.
- **0004** — Language choice (Python+FastAPI) and whether a .NET BFF is needed for SBS operability.
- **0005** — Audit log architecture (hash-chained append-only log, decision provenance, data lineage).
- **0006** — Institution onboarding model (push vs pull, conformance suite design).
- **0007** — SDK generation and distribution (openapi-generator config, distribution via portal vs package registries).
- **0008** — Conformance test suite design.
- **0009** — Per-institution observability (what each institution sees vs what only SBS sees).
- **0010** — DR and backup architecture.
- **0011** — Anexo 1-A as canonical taxonomy + machine-readable distribution.
- **0012** — Normalized complaint indicators (BCB-pattern denominators).
- **0013** — Standards pack versioning policy (how SBS amends taxonomy without breaking institutions).
- **0014** — Dev LLM stack (Ollama vs Qwen vs remote GPU). Flagged for second-opinion with Antoine.
- **0015** — Cross-review LLM backend: Azure OpenAI via WBG tenancy. Added mid-prompt when we corrected from personal OpenAI to WBG-tenanted Azure OpenAI.

Each ADR is written when the work for that decision begins. We do not pre-write ADRs in batch; we write them when the decision is being made so they reflect actual context.

---

## What's deferred to later prompts

Prompt 1 deliberately did not do these things — each is deferred to a specific later prompt:

- **uv project initialization** — Prompt 3
- **Static analysis toolchain** (ruff, pyright strict, gitleaks, commitlint, spectral) — Prompt 4
- **Docker Compose data plane** (Postgres+pgvector, Redis) — Prompt 5
- **Docker Compose LLM bridge** (Ollama local + vLLM in prod) — Prompt 6 (flagged for second-opinion with Antoine)
- **Docker Compose observability** (OpenTelemetry, Prometheus, Loki, Grafana) — Prompt 7
- **GitHub Actions CI** — Prompt 8
- **ADR 0001 content** — Prompt 9
- **Supply chain hygiene** (Syft for SBOM, cosign for signing, gitsign for commits, SLSA build provenance, SOPS+age for secrets) — Prompt 2 (next)

The deferred items aren't gaps. They're the planned sequence. Each lands when its dependencies are in place.

---

## Known gaps to fix in Prompt 2

Three small issues surfaced during Prompt 1's closeout that need fixing:

1. **`close_prompt.py` doesn't `git add` the cross-review file before commit.** The cross-review report is generated but doesn't land in the PR. Two-line fix: `subprocess.run(["git", "add", str(cross_review_path)])` after the cross-review subprocess succeeds.

2. **Deploy-test regex is too broad.** `scripts/setup_hooks.sh` matches the `scripts/setup_*` pattern, triggering a false-positive "infrastructure changed, run fresh-machine test" warning. Tighten the regex to `scripts/setup_(env|cluster|deploy|ci)`.

3. **Two session journal files** ended up on the merged branch — the hand-written one (real, with Azure mid-prompt correction) and a script-generated stub. Keep the manual one; delete the script-generated one. Already in the merged commit; can be cleaned up via a small follow-up commit or just left as a known quirk in the audit trail.

All three are non-blocking. They'll be addressed in Prompt 2.

---

## Glossary

This is for the non-engineer audience. Skim if you know these terms.

**ADR (Architectural Decision Record).** A structured document capturing a significant architectural decision. Has a status, context, decision, consequences, and alternatives considered. Lives in `docs/adr/`.

**Anexo 1-A.** The Peruvian SBS taxonomy (from Resolución SBS N° 04036-2022 and its annexes) defining how complaint data is categorized. The canonical reference all components build on.

**API (Application Programming Interface).** A contract describing how two pieces of software talk to each other. For us, supervised institutions talk to SBS via the Tier 1 API.

**Azure OpenAI.** Microsoft's offering of OpenAI's models hosted within Azure's tenancy isolation. Has governance and data-handling guarantees that personal OpenAI doesn't.

**Branch (in git).** A pointer to a sequence of commits. The default branch is `main`. Feature branches are created for new work and merged back into `main` via PRs.

**Branch protection.** GitHub setting that prevents direct pushes to a branch (like `main`), requiring changes to go through PRs with rules.

**CI (Continuous Integration).** Automated testing that runs on every code change. We don't have CI yet — it lands in Prompt 8.

**Claude Code.** Anthropic's AI-assisted development tool. Reads `.claude/` configuration from the repo to load subagents and slash commands.

**Closeout pipeline.** Our `/close-prompt` workflow that runs reviews, generates a session journal, and pushes a feature branch to a PR with an explicit approval gate.

**Code owners.** A `.github/CODEOWNERS` file mapping file paths to required reviewers.

**Commit.** A snapshot of the repository at a point in time, with an author, timestamp, message, and cryptographic hash.

**Compose (Docker Compose).** Tool for defining and running multi-container Docker applications locally.

**Conventional Commits.** A specification for commit message formatting: `<type>: <description>`. Types include `feat`, `fix`, `chore`, `docs`, etc. Enables automated changelog generation.

**Dependabot.** GitHub's automated dependency-update service. Opens PRs to update outdated dependencies.

**gitsign.** Sigstore's tool for cryptographically signing commits without key management overhead. Coming in Prompt 2.

**GitHub Flow.** A branching strategy: `main` is always deployable, all work happens on feature branches, branches are merged via PRs after review.

**Helm.** The package manager for Kubernetes. Helm charts define how to deploy applications to a Kubernetes cluster.

**MCP (Model Context Protocol).** Anthropic's standard for tools that AI agents can call. We use it for the agent layer's tool integrations.

**mTLS (mutual TLS).** A security protocol where both client and server present certificates to authenticate each other. Used in our API between SBS and supervised institutions.

**OpenAPI.** A specification for describing HTTP APIs. Version 3.1 is current. Tools generate client SDKs and documentation from OpenAPI specs.

**OCI (Open Container Initiative).** The standard format for containers. Docker images are OCI containers.

**PR (Pull Request).** A proposal to merge changes from one branch into another, with discussion, review, and approval before merging.

**RFC 9457.** An IETF standard for machine-readable HTTP error responses. We use it for the API's error catalogue.

**SBOM (Software Bill of Materials).** A list of every component (library, version, license) in a software artifact. Required by many regulatory regimes.

**SLSA (Supply-chain Levels for Software Artifacts).** A framework for build-process integrity attestations. Coming in Prompt 2.

**Squash-merge.** A way to merge a PR that combines all the PR's commits into a single commit on the target branch. Keeps history clean.

**Subagent.** A specialized AI reviewer in Claude Code, defined by a markdown file in `.claude/agents/`. Each subagent has a focused role and runs against specific changes.

**vLLM.** An open-source LLM serving framework. Used in production for serving Qwen 2.5 14B Instruct on-premises.

**Zscaler.** Corporate SSL inspection proxy used by WBG. Intercepts outbound HTTPS, requires Python to trust its root certificate.

---

## Quick reference — file map

```
sbs-peru-sandbox/
├── CLAUDE.md                          ← Project constitution
├── README.md                          ← Repo entry point
├── LICENSE                            ← Placeholder, pending legal review
├── SECURITY.md                        ← Vulnerability disclosure
├── CODE_OF_CONDUCT.md                 ← Contributor Covenant
├── .env.example                       ← Template for required env vars
├── .gitignore                         ← Files git should not track
│
├── .claude/
│   ├── agents/                        ← Six specialized subagents
│   │   ├── reviewer.md
│   │   ├── architect-guard.md
│   │   ├── doc-sync.md
│   │   ├── regulator-readability.md
│   │   ├── second-opinion.md
│   │   └── benchmark-checker.md
│   └── commands/                      ← Eight slash commands
│       ├── part-start.md
│       ├── part-review.md
│       ├── cross-review.md
│       ├── second-opinion.md
│       ├── benchmark-check.md
│       ├── decision-log.md
│       ├── adr-new.md
│       └── close-prompt.md
│
├── .github/
│   ├── pull_request_template.md
│   ├── CODEOWNERS
│   ├── dependabot.yml
│   └── ISSUE_TEMPLATE/
│       ├── bug.md
│       ├── feature.md
│       ├── adr-request.md
│       └── second-opinion-needed.md
│
├── scripts/
│   ├── cross_review.py                ← Azure OpenAI critique script
│   ├── close_prompt.py                ← Closeout pipeline orchestrator
│   ├── setup_hooks.sh                 ← Pre-push hook installer
│   └── requirements-harness.txt       ← Python deps for the harness scripts
│
└── docs/
    ├── PLAN.md                        ← Full plan, Parts 1–11
    ├── DECISIONS.md                   ← Append-only decision log
    ├── CONTRIBUTING.md                ← Workflow walkthrough
    ├── DEPLOY.md                      ← Deployment guide (scaffolded)
    ├── DEMO.md                        ← (Pre-existing; references old structure)
    ├── sprint-input-log.md            ← Peru sprint feedback log
    ├── adr/
    │   ├── README.md                  ← ADR index (0001–0015 Proposed)
    │   └── _template.md               ← ADR template
    ├── research/
    │   ├── README.md                  ← Comparator → PLAN.md cross-reference
    │   └── market-comparators.md      ← The market research document
    ├── reviews/                       ← Cross-review reports land here
    ├── sessions/
    │   ├── _template.md               ← Session journal template
    │   └── 2026-05-15-prompt-01-workflow-harness.md
    ├── explainers/                    ← (This document goes here)
    │   ├── README.md
    │   └── prompt-01-workflow-harness.md  ← You are here
    └── prompts/
        └── second-opinion-templates.md
```

---

## How to use what we built (for non-engineers)

You don't have to run any of this yourself. The harness exists for whoever is actively coding to use. But here's how the pieces relate to you:

**If you want to know "what's the current state of the project?"** — Read `docs/PLAN.md` and the most recent session journal in `docs/sessions/`.

**If you want to know "why did we choose X?"** — Look in `docs/adr/` for the relevant ADR. If the question is about a major architectural decision, there should be an ADR for it.

**If you want to know "did anyone double-check this design?"** — Look in `docs/reviews/` for the cross-review report on that change.

**If you want to review a change before it merges to main** — Look at the open PRs on GitHub. Each PR has a summary, files changed, and (eventually, after Prompt 8) automated test results.

**If you want to know "what comparators inform this design?"** — Read `docs/research/market-comparators.md`. Specific sections are mapped to specific PLAN parts in `docs/research/README.md`.

**If you want to add feedback from the Peru in-person sprint** — Append to `docs/sprint-input-log.md` with a date, source, and your input. It'll be triaged and either accepted (with an ADR), deferred, or rejected with a reason.

---

## What comes next

Prompt 2 (Supply chain & secrets) will land:

- Signed commits via gitsign (Sigstore)
- SBOM generation via Syft, vulnerability scanning via Grype, pip-audit for Python deps
- SLSA build provenance scaffolding
- Secret management foundation via SOPS+age
- The three known gaps from Prompt 1 (cross-review file staging, deploy-test regex, session journal dedup)
- Zscaler/SSL documentation in `docs/CONTRIBUTING.md`
- ADR 0002 begun (deployment topology and PII boundary)

After Prompt 2 lands, we'll have a foundation that satisfies SBS InfoSec's "show me the supply chain" question without further work.

Prompts 3–8 then build the actual development environment: uv project, static analysis, Docker Compose for the data plane and observability, GitHub Actions CI. The first product code (Part 2: Data Model & API Skeleton) starts after the environment is complete.

---

## One closing note on the discipline

Everything in Prompt 1 looks like overhead. Reviews, gates, journals, ADRs, market research — none of it ships a feature. None of it generates revenue. None of it directly produces value for SBS or the institutions they supervise.

What it does is make sure that *every subsequent piece of work* is reviewed, documented, audited, and reversible. Over 30+ Prompts, that compounds. By Part 11, we'll have a system where every architectural decision has a written rationale, every change has a cross-model review, every model has a documented evaluation, every deployment is one command, every integrating institution gets the same standard developer experience, and the audit trail can answer any question SBS or World Bank audit asks.

This is what distinguishes a regulator-grade build from a prototype that looks impressive in a demo. Prototypes are easy. Regulator-grade is the work in Prompt 1.

---

*End of Prompt 1 explainer.*
