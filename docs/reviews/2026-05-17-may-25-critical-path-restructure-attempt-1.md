# Cross-model review — may-25-critical-path-restructure

- **Date:** 2026-05-17
- **Model:** gpt-5.4
- **Target:** may-25-critical-path-restructure

---

**Note:** This review was written against an earlier version of the diff that was subsequently revised after benchmark-checker and second-opinion findings (status downgrade to Proposed, tightened Precedent section, rewritten Schedule risk fallback). Preserved for audit. The canonical review for this PR is the sibling file `2026-05-17-may-25-critical-path-restructure.md` without the `-attempt-1` suffix.

---

## Summary

This change does one useful thing clearly: it turns an implicit May 25 delivery expectation into an explicit scope decision, and it records that decision in both `docs/PLAN.md` and an ADR. That is better than letting scope drift.

I do not see a problem with adding ADR 0025 itself. The rationale is plain enough, the deferrals are named, and the fallback path is stated. That is good practice.

The main issues are not with the existence of the ADR, but with what the documents now claim:

1. **The plan now mixes milestone scope, implementation plan, and audience narrative in one file.** `docs/PLAN.md` is becoming both a product roadmap and a demo script. That creates a maintenance risk and makes it harder to tell what is a binding engineering commitment versus a presentation note. See `docs/PLAN.md:33-56`.

2. **Several “May 25 scope” statements are more specific than the underlying plan bullets and may be read as commitments without acceptance criteria.** Examples:
   - Part 2 adds “Alembic baseline”, “Scalar docs site”, and `GET /v1/complaints` empty-list behavior in prose, but these are not reflected as checklist items or acceptance tests in the Part itself. See `docs/PLAN.md:96`.
   - Part 3 says “No reductions” while packing in mTLS, OAuth, HMAC, idempotency, and RFC 9457 in nine days. See `docs/PLAN.md:117`.
   - Part 6 says all five agents will be present in the UI, with three pre-generated, but does not define what “present” means operationally. See `docs/PLAN.md:164`.

3. **The fallback is probably too thin for the audience described.** The ADR says that if Prompts 9–13 slip, the demo can fall back to Tier 1 only, small handcrafted fixtures, no Tier 2, no real UI wiring, no classifier, no live agents. See `docs/adr/0025-may-25-sprint-critical-path.md:63-69`. For a regulator audience expecting “the architecture is real” across ingestion and supervisory workflow, that fallback is credible as an engineering checkpoint, but weak as a kickoff demonstration.

4. **The decision records target months for deferred work, but not decision gates or exit conditions for re-entry.** “Deferred to June/July” is not enough if this is meant to be the authoritative scope record. There is no statement of what evidence will trigger moving a deferred item back into active scope. This matters because the ADR says any drift requires a documented decision. See `docs/adr/0025-may-25-sprint-critical-path.md:59-72`.

5. **There is a direct clash with the project’s stated north-star of one-command deploy.** Part 9 is deferred entirely, and the demo is declared to run on “a Mac with Homebrew services.” See `docs/PLAN.md:231`, `docs/adr/0025-may-25-sprint-critical-path.md:29-31`. That may be the right schedule choice, but the documents should say plainly that the north-star is temporarily not met for May 25. As written, that tension is left implicit.

## Disagreements with primary review

No primary review text was provided, so I cannot compare line by line.

Given the ADR’s “Flagged for cross-model review” section, I will state where I would push back if a primary review was fully supportive:

1. **I would not accept “Part 9 can be fully deferred” without adding a minimum reproducibility bar for the demo.**
   Industry practice for serious demos, even before full production hardening, is at least a scripted local bring-up:
   - Docker Compose for local stack bring-up is common in FastAPI/Postgres projects.
   - Helm/Terraform can wait; scripted local reproducibility should not.
   Comparators: Kubernetes/Helm is too heavy for this stage, but local compose-style bootstrap is standard across reference implementations from CNCF-aligned projects and many government digital service teams.
   Here, “Mac with Homebrew services” is too person-dependent.

2. **I would push back on the claim that Tier 2 must stay full while production readiness is fully deferred, unless a runnable happy-path batch demo already exists.**
   The ADR’s precedent argument for tiered submission is sound. But from a delivery-risk view, Tier 2 plus synthetic data generator plus async processing is a large slice. If nothing exists yet, the plan may be trying to preserve conceptual proportionality at the cost of actual demo credibility.

3. **I would push back on the UI promise in Parts 6 and 8.**
   “All five present in UI” and “dashboard wired to the real API” are expensive words. If a primary review treated those as harmless wording, I disagree. Those are integration commitments, not presentation notes. See `docs/PLAN.md:164`, `docs/PLAN.md:212`.

4. **I would not treat the ADR precedent section as fully complete.**
   It is honest about lacking a direct sprint-phasing comparator. That honesty is good. But if a primary review said the precedent basis is complete, I would disagree. The cited comparators support staged SupTech adoption and synthetic data use, not the specific minimum-credible-demo cut line chosen here. See `docs/adr/0025-may-25-sprint-critical-path.md:37-52`.

## Risks not flagged elsewhere

1. **Authority confusion between PLAN, ADR, and execution tracker**
   `docs/PLAN.md` now says it is the place where each Part’s May 25 scope is documented. The ADR then says `PLAN.md is the authoritative record of May 25 scope`. See `docs/PLAN.md:46-48`, `docs/adr/0025-may-25-sprint-critical-path.md:59`.
   But there is still no visible short-form execution tracker for daily status against this scope. That creates a governance gap:
   - ADR = decision
   - PLAN = roadmap
   - missing = current sprint board / status source of truth

2. **Named audience list may age badly and creates unnecessary document churn**
   Both files list specific roles and stakeholders in full prose. See `docs/PLAN.md:35-38`, `docs/adr/0025-may-25-sprint-critical-path.md:11`.
   That is useful once, but in planning documents it tends to rot and cause unnecessary edits when attendees change. A stable label like “SBS policy and technical reviewers, plus WBG delivery team” would age better, with named attendees kept in meeting notes.

3. **“Full / reduced / deferred” is not tied to test evidence**
   The documents classify scope, but not how each class will be evidenced by May 25. For example:
   - Full: must be demonstrated live?
   - Reduced: can include mocked or pre-generated outputs?
   - Deferred: must have stubbed interface or no artifact at all?
   Without this, there is room for misunderstanding, especially for Parts 5, 6, 8, and 11.

4. **Pre-generated agent outputs create a provenance and explainability risk**
   Part 6 says three agents will ship pre-generated output. See `docs/PLAN.md:164`, `docs/adr/0025-may-25-sprint-critical-path.md:25`.
   For a regulator audience, that is acceptable only if the UI and script make it unmistakable which outputs are live and which are static exemplars. If not, it will look like the system is doing more than it really is.

5. **The standards-pack claim may outrun the artifact**
   Part 7 and Part 11 say “OpenAPI + JSON Schema published as v0.1 standards pack.” See `docs/PLAN.md:194`, `docs/PLAN.md:271`, `docs/adr/0025-may-25-sprint-critical-path.md:26-28`.
   “Published” implies discoverability, versioning, and stable retrieval. If this ends up as files in the repo without release packaging, checksum, or clear version stamp, the wording will overstate the result.

6. **Schedule compression is hidden inside “closed prompts” wording**
   The 13-prompt sequence is written as if prompts are near-linear and bounded. See `docs/PLAN.md:40-44`. In practice, Prompts 6-8 contain cross-cutting design decisions that often cause rework in scaffolding, auth, and schema contracts. The plan does not acknowledge likely rework loops.

7. **The fallback path does not preserve the stated “minimum lovable demo”**
   Earlier in `PLAN.md`, the project’s minimum lovable demo is: signed mTLS `POST /v1/complaints` → validated → persisted → event emitted → audit log → trace in Grafana. See `docs/PLAN.md:31`.
   The fallback in the ADR talks about Tier 1 only and small fixtures, but does not explicitly restate that the event, audit log, and trace chain must still be shown. That omission matters because “API working end-to-end” can be read too loosely.

## Recommended actions

1. **Add a short “May 25 acceptance table”**
   Put it either in `docs/PLAN.md` or as a separate `docs/SPRINT-MAY25.md`. For each Part in scope, include:
   - status class: full / reduced / deferred
   - demo evidence
   - test evidence
   - owner
   - latest date to cut scope
   Example columns are enough. This will reduce ambiguity.

2. **Separate roadmap from demo narrative**
   In `docs/PLAN.md`, keep the Part structure and scope labels, but move audience description, prompt sequence, and fallback narrative into the ADR or a sprint brief.
   `PLAN.md:33-56` currently reads partly like an internal briefing note. That makes the plan harder to maintain.

3. **Tighten the wording for reduced and pre-generated functionality**
   For Part 6, explicitly say in both plan and ADR:
   - which two agents are live
   - which three are static exemplars
   - how the UI labels static outputs
   - that static outputs are not represented as live model inference
   This is important for plain-language explainability and audit honesty.

4. **Introduce a minimum reproducible demo command, even if Part 9 stays deferred**
   Do not wait for Helm/Terraform. Add one scripted local bring-up path by May 25:
   - `make demo-up`, or
   - `uv run` plus a documented local dependency bootstrap, or
   - Docker Compose if feasible
   This aligns better with the “one-command deploy” principle than “run on maintainer’s Mac with Homebrew services.”

5. **Change “published” to a more precise term unless release mechanics exist**
   For Parts 7 and 11, if the artifact will only exist in-repo by May 25, say:
   - “generated and version-stamped in the repository”
   Reserve “published” for when there is an actual release location and retrieval path.

6. **Add explicit demo truthfulness rules**
   One small section in the ADR or sprint brief:
   - live components are labeled live
   - pre-generated outputs are labeled exemplar/static
   - synthetic data is labeled synthetic
   - no hidden manual intervention during the demo without disclosure
   This is normal good practice for regulator-facing demonstrations.

7. **Strengthen the fallback definition**
   Amend `docs/adr/0025-may-25-sprint-critical-path.md:63-69` so the fallback still requires the full observable chain from the plan’s minimum demo:
   - authenticated request
   - validation result
   - persistence
   - emitted event
   - audit log entry
   - visible trace
   If any one of these is absent, say so explicitly and downgrade the fallback description.

8. **Add a cut line for Tier 2**
   Because Tier 2 is a large item, define a date after which batch async processing is cut to a simpler happy-path upload and parse demonstration, or fully moved behind a recorded artifact. Without such a cut line, it can consume the schedule and endanger Tier 1.

## Triage

_TODO: human-filled. Disposition each finding above as accept / defer / reject, with reason._
