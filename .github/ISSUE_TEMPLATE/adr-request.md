---
name: ADR request
about: Request an Architectural Decision Record. Use when a decision will be hard to reverse, affects a public contract, or commits the project to a specific approach.
title: "ADR-request: <one-line summary>"
labels: ["adr-request", "architecture"]
---

## Decision needed

One sentence. What decision must be made?

## Why an ADR (not just a decision log entry)

Tick any that apply.

- [ ] Hard to reverse once chosen.
- [ ] Affects a public contract (API, schema, error model, auth).
- [ ] Affects how supervised institutions integrate.
- [ ] Affects the agent architecture (MCP / A2A / LangGraph layer boundaries).
- [ ] Affects the deploy / runtime / data-residency story.
- [ ] Affects how SBS staff operate the platform.

## Forces

What constraints, requirements, or stakeholder asks are in play? Cite the sprint input log entries by date if applicable.

## Alternatives you see

Bullet list. One sentence per option with the tradeoff.

## Precedent

Which comparator from [docs/research/market-comparators.md](../../docs/research/market-comparators.md) is most relevant? If none, flag it — we may need to extend the research document first.

## Target Part / prompt

When does the decision need to land?

## Owner

Who drafts the ADR?
