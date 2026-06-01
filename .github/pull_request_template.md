<!-- Use this template for every PR. The /close-prompt pipeline fills most of it in. -->

## Summary

One paragraph. What changed and why. Plain language. Readable by an SBS reviewer.

## Linked ADR(s)

- ADR-NNNN — _slug_ — status (Proposed / Draft / Accepted / Superseded).

If this PR creates or amends an ADR, list it here. If a locked decision is touched, the ADR amendment must be in this PR.

## North-star principles affected

Tick any that apply, and add a one-line note.

- [ ] 1 — One-command deploy
- [ ] 2 — Configuration over code
- [ ] 3 — Observability as a first-class feature
- [ ] 4 — Standards over inventions; onboarding as product
- [ ] 5 — Plain-language explainability
- [ ] 6 — Built on benchmarked precedent

## Exit criteria progress

Which PLAN.md exit criteria does this PR advance? Reference Part number and the bullet.

- Part N — _bullet_ — ⏳ in progress / ✅ complete.

## Test plan

- [ ] Unit tests added or updated for changed behavior.
- [ ] Integration tests where the change crosses a service boundary.
- [ ] Manual verification — what command was run, what output expected.
- [ ] For UI changes: screenshot or recording attached, browser + viewport noted.

## Subagent verdicts (filled by /close-prompt)

| Subagent | Verdict | Headline finding |
| --- | --- | --- |
| reviewer | | |
| architect-guard | | |
| doc-sync | | |
| regulator-readability | | |
| benchmark-checker | | |
| second-opinion | | |

## Cross-model review

Path to the review file in `docs/reviews/`. Triage line must be filled before merge.

## Screenshots (if UI)

<!-- attach -->

## Reviewer checklist

- [ ] Branch name matches `part-NN/<slug>`.
- [ ] Commit message follows Conventional Commits.
- [ ] No real secrets in the diff (`.env`, `*.pem`, `*.key`, `*.crt`).
- [ ] Documentation updated for any user-visible change.
- [ ] ADRs cited where required by `benchmark-checker`.
- [ ] Session journal added in `docs/sessions/`.
- [ ] CI green.
