# Second-Opinion Prompt Templates

Copy verbatim. Replace [bracketed] sections with specifics.

## Template 1 — ADR sanity check

I'm building a SupTech platform for a financial regulator (consumer complaint ingestion + multi-agent analytics). I'm about to make this architectural decision: [decision]. The constraints are: [constraints]. The alternatives I considered: [alternatives]. My reasoning: [reasoning]. What am I missing? What would you do differently and why? Be specific and direct — I want disagreement if you have it.

## Template 2 — Library/API verification

Does the [library name] [version] have a function/method/feature called [specific thing]? If yes, what's the exact signature and a working example? If no, what's the actual way to do [goal]? Please base your answer only on what you can verify from documentation, not inference.

## Template 3 — Security code review

Review this [auth/signing/encryption] code for security issues. Context: [what it's protecting]. Threat model: [who/what is the attacker]. Code: [paste]. Look specifically for: timing attacks, missing validations, replay vulnerabilities, key handling issues, and deviations from [specific RFC or standard]. Be paranoid.

## Template 4 — Stuck debugging

I'm building [thing]. Expected behavior: [what should happen]. Actual behavior: [what happens]. What I've tried: [list of attempts and outcomes]. Relevant code: [paste]. Relevant logs: [paste]. What are the 3-5 most likely root causes I should investigate, in order of likelihood?

## Template 5 — Architecture review

I'm building a SupTech platform: FastAPI + LangGraph agents exposed via A2A + MCP tools + Postgres + Redis + Next.js, deployed via Helm. Current architecture: [paste architecture summary and ADRs]. Demo target: [paste demo script]. Constraints: solo dev, full scope, must wow a sophisticated technical audience at a financial regulator. Review for: structural issues, missed opportunities, risks I'm not seeing, things that won't hold up under scrutiny by a senior architect. Be direct.

## Template 6 — API spec review

Here's my OpenAPI spec for a regulator-facing API that supervised financial institutions will integrate against: [paste]. Compare against best practices from Open Banking UK, Berlin Group NextGenPSD2, and Brazil's Open Finance. What's missing or weak? What would a bank's integration team criticize in code review?

## Trigger reminders

- ADR moment: Template 1, before locking
- Security-critical code: Template 3, after writing, before merging
- Claude Code in circles >30 min: Template 4
- I assert obscure API detail confidently: Template 2
- End of Parts 2, 5, 8, 10: Template 5 (architecture review)
- End of Parts 2, 10: Template 6 (OpenAPI review)