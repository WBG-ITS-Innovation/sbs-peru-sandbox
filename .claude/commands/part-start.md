---
description: Open a Part. Returns goals, prerequisites, open second-opinion items, and a ready-to-proceed question.
argument-hint: <part-number>
---

Open Part $1 of the SBS SupTech Prototype build.

Do the following, in order:

1. Read [docs/PLAN.md](docs/PLAN.md). Locate the section for "Part $1".
2. Read [docs/PLAN.md](docs/PLAN.md) sections for all prior Parts. List which exit criteria of each prior Part are still unchecked. Those are blocking prerequisites — surface them.
3. Read [docs/DECISIONS.md](docs/DECISIONS.md). List the entries dated since the previous session journal in [docs/sessions/](docs/sessions/) that relate to Part $1.
4. Read [docs/adr/README.md](docs/adr/README.md). List ADRs scheduled for Part $1 (status "Proposed", target prompt/Part = $1).
5. Read the latest file in [docs/sessions/](docs/sessions/). Surface any "deferred" or "flagged" items relevant to Part $1.
6. Read [docs/sprint-input-log.md](docs/sprint-input-log.md). Surface any entries that affect Part $1 scope.
7. Open [docs/research/market-comparators.md](docs/research/market-comparators.md). Identify which comparator sections are most relevant to Part $1's exit criteria.

Produce a single response with these sections:

- **Part $1 — goals.** Quoted exit criteria from PLAN.md verbatim.
- **Prerequisites.** Unchecked items from prior Parts, with the Part number.
- **Open second-opinion items.** Templates triggered for this Part per [docs/prompts/second-opinion-templates.md](docs/prompts/second-opinion-templates.md), and whether each is open or resolved.
- **ADRs to write.** From the ADR queue, with target slug.
- **Relevant comparators.** Section numbers / names in `market-comparators.md` that apply.
- **Sprint inputs.** Anything from the sprint log that affects scope.
- **Ready-to-proceed question.** One specific question for the human (e.g. "Confirm Tier 1 latency target is `target ≤500ms p95 (illustrative)` before I open the OpenAPI spec?").

Do not write code yet. This command is for context-loading and human alignment only.
