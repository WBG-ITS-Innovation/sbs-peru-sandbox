---
description: Scaffold a new ADR with Precedent and Divergence sections required.
argument-hint: <slug>
---

Scaffold a new ADR for slug `$1`.

Steps:

1. Read [docs/adr/README.md](docs/adr/README.md). Determine the next ADR number — one higher than the highest existing or queued ADR.
2. Create a new file at `docs/adr/NNNN-$1.md` (zero-padded to four digits).
3. Use the template below verbatim, filling in the number, slug, date, and active Part.
4. Add the new ADR to the index in [docs/adr/README.md](docs/adr/README.md) with status `Proposed`.
5. Echo the path to the human and remind them: the `## Precedent` and `## Divergence` sections must be filled before this ADR can move to `Accepted`, and `benchmark-checker` will block any merge that doesn't.

ADR template:

```markdown
# ADR NNNN — <Title from slug>

- **Status:** Proposed
- **Date:** YYYY-MM-DD
- **Part:** N
- **Authors:** <name>

## Context

What problem is this ADR solving? What forces are in play? Two paragraphs maximum.

## Decision

What we are doing. One paragraph. Specific, named, verifiable.

## Precedent

Cite at least one comparator from docs/research/market-comparators.md. Name the section. Explain in one sentence what the comparator does that this decision adopts or adapts.

- <Comparator> (docs/research/market-comparators.md §X.Y) — what they do, what we adopt.

## Divergence

If we diverge from any cited comparator, name the divergence and the reason. If we don't diverge, say "no material divergence".

## Consequences

What gets easier. What gets harder. What is now locked.

## Alternatives considered

List the alternatives and one sentence each on why they were rejected.

## Open questions

What we don't know yet. Each open question gets an owner and a target date.
```
