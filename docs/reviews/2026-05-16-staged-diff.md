# Cross-model review — staged-diff

- **Date:** 2026-05-16
- **Model:** gpt-5.4
- **Target:** staged-diff

---

## Summary

This change is moving in the right direction. It fixes a real gap in the benchmark-checker guidance by allowing citations to the correct research file under `docs/research/`, not only `market-comparators.md`. It also adds useful guardrails for secrets, dependency review, and closeout workflow handling.

The main issues I see are these:

1. **The accepted ADRs overstate current control strength in a few places.**
   - `docs/adr/0016-secret-scanner-stack.md:20`, `:34-40`, `:43-44`
   - The repository now commits a stub `.secrets.baseline`, while the ADR is already marked `Accepted`. That means the local `detect-secrets` control is not in a canonical, reproducible state yet.
   - This is not fatal, but the wording should reflect that this is a transition state, not a settled operating model.

2. **`SECURITY.md` still does not provide a concrete external disclosure path.**
   - `SECURITY.md:9-10`
   - “security@<TBD>” and “address listed in the repository profile” are not regulator-grade disclosure instructions. For a repo that now adds several security controls, this remains a governance gap.

3. **The new dependency-review workflow may not behave as described in the comments.**
   - `.github/workflows/dependency-review.yml:4-5, 30-32`
   - The comment says moderate findings are “reported but non-blocking,” but the configuration shown only comments `on-failure`. That means non-blocking moderate findings may be visible only in logs, not surfaced in the PR discussion. The ADR partly acknowledges this (`docs/adr/0019-dependency-review-threshold-high.md:24-25`), but the workflow header comment reads more strongly than the implementation supports.

4. **The closeout script now hard-fails on missing Azure env unless a skip reason is given. That is deliberate, but onboarding and one-command use take a hit.**
   - `scripts/close_prompt.py:337-365`, `docs/CONTRIBUTING.md:134`
   - This is a valid policy choice, but it makes the local default path stricter than before. For a solo-maintainer project, that is acceptable only if the bypass path is clearly documented everywhere the old flag appeared. This diff updates the main contributor doc, but I would still check for stale references elsewhere.

5. **The new WBG/Zscaler setup guide is useful, but it is being linked from authoritative docs while explicitly unverified.**
   - `CLAUDE.md:46-47`, `SECURITY.md:47-50`, `docs/CONTRIBUTING.md:40-42`, `docs/setup/corporate-proxy-and-zscaler.md:1-4`
   - That is acceptable if treated as draft operational guidance. It should not become a hidden prerequisite for basic onboarding without a verification pass on a clean machine.

## Disagreements with primary review

I agree with most of the cross-model review in `docs/reviews/2026-05-16-staged-diff.md`. I differ on a few points.

1. **I would not push ADR 0016 back from `Accepted` to `Proposed` solely because the baseline is currently a stub.**
   - `docs/adr/0016-secret-scanner-stack.md:20, 34-36`
   - The architectural decision is clear enough to accept now: two local scanners, one CI gate. The problem is not that the decision is unmade; the problem is that one implementation detail is transitional and should be labeled more sharply.
   - I would keep `Accepted`, but add an explicit “temporary operational exception” sentence and a tracked follow-up.

2. **I do not think the benchmark precedent claim is as weak as the primary review suggests, but it should still be narrowed.**
   - `docs/adr/0016-secret-scanner-stack.md:29-31`
   - Saying this pattern is “the established default in mature open-source security tooling” is broader than the cited evidence supports.
   - But the answer is not that the precedent is missing; it is that the wording should say “common pattern” or “well-established pattern” rather than “established default.”

3. **I would treat the missing `gitleaks` suppression story as a second-order issue, not a blocker for this diff.**
   - The primary review is right that false-positive management matters.
   - Still, in this repo state, the bigger operational risk is the stub baseline and ambiguous disclosure path. A dedicated `gitleaks.toml` can follow once real false positives appear.

4. **I think the close_prompt hard-fail change is justified and better than the old silent skip.**
   - `scripts/close_prompt.py:319-365`
   - The primary review focuses on friction. I would put more weight on auditability here. Silent success on missing cross-review credentials was the worse design.

## Risks not flagged elsewhere

1. **Dependabot labels no longer match the documented label taxonomy by ecosystem**
   - `.github/dependabot.yml:23-24, 38-43, 58-63`
   - All three ecosystems now get `dependencies` and `security`, but `scripts/bootstrap_github_labels.sh:23-25` still defines `ci`, `python`, `javascript`, and `docker` labels, and the earlier Dependabot file used those ecosystem labels.
   - This is not a runtime bug, but it weakens triage and routing. If CODEOWNERS or review habits expect language/ecosystem labels, the current config drops that signal.

2. **The secret-scan workflow comment claims PR commit-history coverage, but the action configuration does not show the scan mode explicitly**
   - `.github/workflows/secret-scan.yml:20-23`
   - The comment says full history is required so gitleaks can scan all commits in the PR, but the workflow only uses `gitleaks/gitleaks-action@v2` without visible scan arguments.
   - If the action defaults change, or if its default mode is not PR-history-aware, the comment becomes inaccurate. In regulator-facing controls, comments about security coverage should match explicit configuration, not assumptions.

3. **`.gitignore` broadening may hide legitimate tracked local config patterns without a corresponding negation rule**
   - `.gitignore:42-49`
   - The ADR correctly says `.env.example` is the only exception, but this diff does not show a negation rule such as `!.env.example`.
   - If `.env.example` is already tracked, Git will keep tracking it, so this may not break today. But it is fragile for future clones, renames, or additional templates such as `.env.test.example`. This should be explicit in `.gitignore`, not only in prose.

4. **The dependency-review workflow does not cover GitHub Actions dependency changes themselves**
   - `.github/workflows/dependency-review.yml:9-15`
   - It triggers on package manifests and on its own workflow file, but not on other workflow files that may change `uses:` references.
   - Since `.github/dependabot.yml` now watches `github-actions`, industry practice is usually to also review workflow dependency changes when workflow files change. GitHub’s own dependency-review action is commonly scoped more broadly on repos that treat Actions as part of supply chain. Comparator: GitHub Secure Use guidance; OpenSSF Scorecard’s focus on pinned and reviewed workflows.

5. **The supply-chain research file is useful, but some sections are too assertion-heavy for the citation rule being enforced**
   - `docs/research/supply-chain-precedents.md:14-31`
   - The benchmark-checker now treats any research file under `docs/research/` as authoritative precedent. That raises the quality bar for those files.
   - Some sentences in this new file read as synthesis without enough citation granularity inside the research artifact itself, for example “Several CFPB and UK GDS open-source repos use `high` as their default” (`docs/research/supply-chain-precedents.md:29-31`).
   - If this file becomes the basis for blocking ADR checks, it will need source hygiene closer to what one would expect in an audit appendix, not just a living note.

6. **The “maintainer only” label bootstrap introduces a hidden repo-state dependency**
   - `docs/CONTRIBUTING.md:30-38`, `scripts/bootstrap_github_labels.sh:1-55`
   - Several docs now assume labels exist, but there is no machine-checked preflight ensuring the repo has been bootstrapped.
   - In a fresh repo or transferred repo, automation may still run, but triage conventions and any label-dependent process will silently degrade. One-command deploy and product-grade onboarding usually mean either automatic provisioning or a startup check that fails clearly.

7. **The cross-review artifact naming can collide across repeated same-day runs**
   - `docs/reviews/2026-05-16-staged-diff.md`, `scripts/close_prompt.py:319-365`
   - This diff shows a date-based review artifact path and the closeout script expects one output file. If `scripts/cross_review.py` uses only date + target naming, repeated same-day runs against staged state can overwrite prior review records.
   - For an audit trail, timestamp or commit-hash based naming is safer. I cannot confirm the implementation of `cross_review.py` from this diff alone, but the visible artifact name suggests collision risk.

## Recommended actions

1. **Tighten ADR 0016 wording to match the actual current state**
   - Update `docs/adr/0016-secret-scanner-stack.md:20, 34-44`
   - Suggested changes:
     - replace “established default” with “common pattern”
     - state plainly that `.secrets.baseline` is temporarily non-canonical
     - say local `detect-secrets` is an added local control, not a guaranteed gate

2. **Add a concrete follow-up item for the stub baseline**
   - Either in ADR 0016 consequences or in `docs/DECISIONS.md`
   - Make it explicit:
     - owner
     - trigger: maintainer installs `detect-secrets`
     - output: canonical baseline regenerated and reviewed
   - Right now it is documented, but not operationally assigned.

3. **Fix the disclosure path in `SECURITY.md` before wider exposure**
   - `SECURITY.md:9-10`
   - Replace placeholders with one real mailbox or one real named contact method.
   - “See repo profile” is not enough for vulnerability reporting.

4. **Make the dependency-review workflow comment match the actual behavior**
   - `.github/workflows/dependency-review.yml:3-5, 30-32`
   - Either:
     - change the comment to say moderate issues are visible in logs and only commented when the job fails, or
     - configure the action to always produce a PR summary if that is supported by the chosen version.

5. **Add explicit negation(s) in `.gitignore` for allowed examples**
   - `.gitignore:39-49`
   - At minimum:
     - `!.env.example`
   - If you expect more templates later, define the pattern now instead of relying on “already tracked” behavior.

6. **Make secret-scan coverage explicit in workflow config, not only comments**
   - `.github/workflows/secret-scan.yml:20-30`
   - If the intent is history-aware scanning, pin that in arguments or action inputs rather than relying on action defaults.
   - This matters because the comments describe a stronger control than the visible configuration proves.

7. **Broaden dependency-review triggers to workflow file changes if GitHub Actions are part of the managed dependency surface**
   - `.github/workflows/dependency-review.yml:9-15`
   - Consider adding:
     - `.github/workflows/**`
   - This is consistent with adding `github-actions` to Dependabot and with common GitHub-native supply-chain practice.

8. **Align Dependabot labels with the documented taxonomy**
   - `.github/dependabot.yml`, `scripts/bootstrap_github_labels.sh`
   - Decide one of these:
     - keep only `dependencies` and `security`, and remove stale label expectations elsewhere
     - or restore per-ecosystem labels like `python`, `javascript`, `ci`
   - Right now the repo defines both schemes.

9. **Raise the evidence standard inside `docs/research/supply-chain-precedents.md`**
   - Add short source notes or footnotes per section, especially where the file makes comparative claims across named public-sector repos.
   - Once benchmark-checker can block ADRs based on this file, the file itself becomes part of the control system.

10. **Check for stale references to `--no-cross-review` outside the edited docs**
    - `scripts/close_prompt.py:380-392`, `docs/CONTRIBUTING.md:134`
    - This diff updates the main contributor path, but a repo-wide grep should confirm there are no old instructions left in prompts, templates, or session docs.

## Triage

_TODO: human-filled. Disposition each finding above as accept / defer / reject, with reason._
