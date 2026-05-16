---
name: Second opinion needed
about: Flag a decision, design, or piece of code for cross-model review.
title: "second-opinion: <one-line summary>"
labels: ["second-opinion"]
---

## What needs a second opinion

One paragraph. What is the artifact under review? Link to the file, PR, or ADR.

## Which template

From [docs/prompts/second-opinion-templates.md](../../docs/prompts/second-opinion-templates.md):

- [ ] Template 1 — ADR sanity check
- [ ] Template 2 — Library / API verification
- [ ] Template 3 — Security code review
- [ ] Template 4 — Stuck debugging
- [ ] Template 5 — Architecture review
- [ ] Template 6 — API spec review

## Which model

- [ ] GPT-5 (default, via `/cross-review`)
- [ ] Gemini 2.5 Pro
- [ ] Claude Opus 4.x (different session)
- [ ] Other — specify

## What you want to know

The specific question. Not "is this good" — "is the HMAC verification window of 5 minutes safe given the clock-skew risk on SBS-side NTP".

## Acceptance — what counts as a useful answer

How will you know the second opinion was useful? E.g. "names at least one concrete weakness or confirms the design is sound with a specific reason".

## Triage owner

Who reads the cross-review output and dispositions it in the session journal?
