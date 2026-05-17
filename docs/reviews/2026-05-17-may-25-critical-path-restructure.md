# Cross-model review — may-25-critical-path-restructure

- **Date:** 2026-05-17
- **Model:** gpt-5.4
- **Target:** may-25-critical-path-restructure

---

## Summary

This change makes an important planning decision explicit: May 25 is now treated as a scoped sprint kickoff, not as the full July delivery. That is the right kind of decision to record in writing.

I agree with the core move: document the cut, document the deferrals, and stop silent scope drift.

The main issues are in how the decision is expressed.

1. **`PLAN.md` is now mixing three different things in one place**: product plan, sprint control, and demo narrative.
   See `docs/PLAN.md:33-56`.
   The new “May 25 sprint kickoff critical path” section includes audience description, prompt sequence, fallback narrative, and escalation path. Those are useful, but they are not all the same kind of document. This will make the plan harder to maintain and easier to contradict later.

2. **Several new “May 25 scope” paragraphs read like firm commitments without matching acceptance criteria.**
   Examples:
   - `docs/PLAN.md:96` adds “Alembic baseline”, “Scalar docs site”, and `GET /v1/complaints` behavior.
   - `docs/PLAN.md:117` says Part 3 is full scope with mTLS, OAuth, HMAC, idempotency, and RFC 9457.
   - `docs/PLAN.md:164` says all five agents are present in the UI, but three are pre-generated.
   - `docs/PLAN.md:212` says the dashboard is wired to the real API.
   These are now commitments in prose, but there is no matching “done means” table.

3. **The fallback case is still weak for the audience described.**
   The fallback in `docs/PLAN.md:50-56` and `docs/adr/0025-may-25-sprint-critical-path.md:63-67` reduces the demo to Tier 1 signed ingestion plus architecture story for the rest. That may be enough for an internal engineering checkpoint. It is thin for a regulator-facing kickoff where trust depends on seeing more than an API call succeed.

4. **There is an unresolved conflict with the project’s own principles.**
   The project says “one-command deploy” is a north-star principle. But Part 9 is fully deferred and the demo is explicitly planned to run “on a Mac with Homebrew services.” See `docs/PLAN.md:231` and `docs/adr/0025-may-25-sprint-critical-path.md:29-31`.
   That may be the right trade-off. But it should be stated plainly as a temporary exception, not left implicit.

5. **The ADR is honest about lacking direct precedent, which is good.**
   I do not see fabrication here. The downgrade to Proposed and the explicit blocker in `docs/DEFERRED.md:81-87` are the right move. That said, the decision is still only partially grounded in precedent. It is grounded in domain comparators, not in sprint-phasing comparators.

## Disagreements with primary review

The prior review file already catches several important points. I agree with most of it. My disagreements are about emphasis.

1. **I would push harder on the missing acceptance criteria problem.**
   The earlier review notes that some scope statements are more specific than the underlying plan bullets. I think this is the main documentation defect in this diff, not a secondary one.
   For a regulator-grade project, “full / reduced / deferred” is not enough. Each scoped item should say what evidence proves it exists by May 25:
   - live demo
   - automated test
   - recorded artifact
   - static exemplar
   - architecture-only

2. **I would be stricter on the use of “published” for the standards pack.**
   The earlier review raises this as wording risk. I think it is more than wording.
   `docs/PLAN.md:194`, `docs/PLAN.md:271`, and `docs/adr/0025-may-25-sprint-critical-path.md:26-28` say the standards pack will be “published.” If this means files generated in the repo, that is not yet publication in the normal sense used by standards bodies or public-sector digital teams.
   Comparator practice here would be things like:
   - OpenAPI Initiative style released artifacts
   - GitHub Releases with versioned downloadable assets
   - OCI artifacts
   - government standards pages with stable retrieval URLs
   If those mechanics are not in place, “generated and version-stamped” is more accurate.

3. **I think the audience list should be moved out of the plan.**
   The earlier review calls this churn risk. I agree, but I would go further.
   `docs/PLAN.md:35-38` and `docs/adr/0025-may-25-sprint-critical-path.md:11` name specific reviewer roles in long prose. That belongs in a sprint brief or meeting note, not in the enduring plan and ADR. The documents should describe the audience class, not the attendee list.

4. **I am less convinced that Tier 2 must remain “full” for May 25.**
   The earlier review questions this. I agree.
   `docs/PLAN.md:132` keeps Tier 2 full while Part 9 is fully deferred. For a nine-day window, batch upload plus async processing plus synthetic data generation is a large chunk. Unless there is already working code off-diff, this may be the wrong item to defend as “full”.

## Risks not flagged elsewhere

1. **No explicit truth-labeling rule for live vs static behaviour**
   Part 6 says two agents are live and three ship pre-generated output. See `docs/PLAN.md:164` and `docs/adr/0025-may-25-sprint-critical-path.md:25`.
   There is no rule saying the UI and demo script must label:
   - live agent output
   - pre-generated exemplar output
   - synthetic data
   - manual operator steps
   Without that, the demo can accidentally overstate what is real.

2. **“Authoritative record” is assigned to `PLAN.md`, but there is no sprint control document**
   The ADR says `PLAN.md` is the authoritative record of May 25 scope. See `docs/adr/0025-may-25-sprint-critical-path.md:59`.
   But `PLAN.md` is still a long-lived roadmap document, not a sprint tracker. There is still no concise source of truth for:
   - current status
   - cut decisions
   - blocked items
   - owner
   - latest safe date to drop scope
   That gap matters more now that the sprint is explicitly time-boxed.

3. **The fallback path does not restate the minimum observable chain**
   Earlier in `PLAN.md`, the “minimum lovable demo” is explicit: signed mTLS request, validation, persistence, event emitted, audit log, trace in Grafana. See `docs/PLAN.md:31`.
   The fallback text at `docs/PLAN.md:50-56` and `docs/adr/0025-may-25-sprint-critical-path.md:63-67` says Tier 1 ingestion end-to-end, but does not restate the observable chain. That leaves room for “end-to-end” to degrade into “request returns 201”.

4. **“Reduced” scope is not consistently defined**
   Across Parts 5, 6, 8, and 11, “Reduced” means different things:
   - one live subset of a larger capability
   - UI wired but management flows absent
   - static outputs shown in place of live outputs
   - standards artifacts generated without governance or packaging
   That is manageable, but the term is being used loosely. A reader cannot tell whether “reduced” means operational subset, static placeholder, or documentation-only.

5. **The “one-command deploy” principle may be weakened by precedent if not explicitly called an exception**
   If this document stands without a plain note that May 25 is an exception to the deploy principle, it sets an internal pattern: milestone pressure can bypass one-command reproducibility.
   On a solo-maintained project, that kind of precedent tends to stick.

6. **The prompt-sequence framing hides cross-prompt rework**
   `docs/PLAN.md:40-47` presents the remaining work as a clean sequence. In practice:
   - OpenAPI decisions affect models and validation
   - auth design affects gateway and app behaviour
   - UI wiring often exposes API contract gaps
   - batch ingestion often forces model or storage changes
   The plan does not name rework loops, which matters for a nine-day schedule.

7. **Deferred months are named, but no cut gates are**
   The docs say many things are deferred to June or July. They do not say when an item must be cut if it is not ready by a certain date.
   Example: if Tier 2 is not demoable by Day 6, does it stay in active scope, move to recorded artifact, or drop entirely? The documents do not say.

## Recommended actions

1. **Add a one-page May 25 acceptance table**
   Put it in a new file such as `docs/SPRINT-MAY25.md` or a short section in `PLAN.md`.
   For each Part in May 25 scope, include:
   - scope class: full / reduced / deferred
   - evidence type: live / recorded / static exemplar / architecture only
   - acceptance check
   - owner
   - latest cut date
   This is the biggest missing control.

2. **Move demo narrative out of `PLAN.md`**
   Keep per-Part May 25 scope notes in `PLAN.md`.
   Move the following out to a sprint brief:
   - named audience prose
   - 13-prompt narrative
   - detailed fallback story
   - escalation wording
   `PLAN.md` should remain a durable plan document, not also a briefing note.

3. **Add explicit demo honesty rules**
   In ADR 0025 or the sprint brief, add a short section:
   - synthetic data must be labeled synthetic
   - pre-generated outputs must be labeled exemplar/static
   - live outputs must be labeled live
   - any manual intervention during the demo must be disclosed
   This is especially important for Part 6.

4. **State the temporary exception to the deploy principle**
   Add one sentence in ADR 0025 and possibly in `PLAN.md`:
   - May 25 does not meet the “one-command deploy” north-star
   - this is a deliberate temporary exception
   - minimum compensating control is a documented local bring-up script
   That makes the trade-off explicit.

5. **Replace “published” unless release mechanics exist by May 25**
   In:
   - `docs/PLAN.md:194`
   - `docs/PLAN.md:271`
   - `docs/adr/0025-may-25-sprint-critical-path.md:26-28`
   change “published” to “generated and version-stamped in the repository” unless there will actually be:
   - a stable retrieval location
   - a version tag or release
   - checksums or equivalent integrity marker

6. **Tighten the fallback wording to preserve observability**
   Amend the fallback text in both `PLAN.md` and ADR 0025 so it explicitly requires the full minimum chain:
   - authenticated request
   - schema validation
   - persistence
   - emitted event
   - audit log entry
   - visible trace in Grafana
   If any of those are not guaranteed in fallback, say so directly.

7. **Add cut lines for the largest risky items**
   At minimum, define cut dates for:
   - Part 4 Tier 2 async batch path
   - Part 6 live agents beyond the first two
   - Part 8 dashboard wiring
   Example: if not integrated by Day 6, switch to recorded artifact or defer. Without cut lines, these items can consume the sprint.

8. **Reconsider whether Part 4 should stay “full”**
   Unless there is already hidden implementation progress, the combination of:
   - batch upload
   - async processing
   - synthetic generator
   - same taxonomy mapping
   may be too much for the time left. A narrower and safer May 25 position would be:
   - Tier 1 full and live
   - Tier 2 happy-path only or recorded artifact
   - generator reduced to one deterministic scenario
   I would review this before locking it further.

## Triage

**Summary findings (5):**

1. **PLAN.md mixes plan + sprint control + demo narrative.** DEFER — accepted as a real architectural critique but out of scope for Prompt 4 (paper-only scope-lock). Open as a follow-up: extract sprint-control prose (the "May 25 sprint kickoff critical path" section's audience/escalation paragraphs) into a separate `docs/sprint-briefs/2026-05-25-lima.md` once Prompt 5 lands. PLAN.md keeps per-Part scope subsections (which are durable plan content).

2. **No "done means" acceptance criteria for Full/Reduced/Deferred.** ACCEPT-AND-DEFER — valid finding; the per-Part scope statements should reference acceptance criteria, not just deliverables. Targeted for Prompts 5-8 — each Part's first prompt adds explicit "May 25 acceptance" checklist items in its checklist section, anchored to the per-Part May 25 scope subsection landing here.

3. **"Published" overclaims v0.1 standards pack.** ACCEPT — fix the wording in this PR. Change "published as the v0.1 standards pack" → "generated and version-stamped as the v0.1 standards pack" in PLAN.md Part 7 May 25 scope subsection and ADR 0025 Part 7 reduced-scope bullet.

4. **Decision gates / exit conditions for deferred work not stated.** DEFER — accepted; addressed implicitly by the Promotion criteria pattern (ADR 0025 has one) and the existing DEFERRED.md entries. Tighten in a follow-up DEFERRED.md hygiene pass. Not in scope tonight.

5. **One-command-deploy north-star silently violated by Mac+Homebrew fallback.** ACCEPT — fix in this PR. Add one explicit sentence to ADR 0025 Consequences: "This decision is a deliberate, time-bounded exception to CLAUDE.md north-star principle #1 (one-command deploy). The exception ends when Part 9 lands (June/July 2026)." Same wording optional in PLAN.md Part 9 May 25 scope subsection.

**Disagreements with primary review (4):**

D1. **Part 9 fully deferred without scripted local bring-up.** DEFER — accepted as a real risk but scoping a scripted local bring-up tonight expands Prompt 4 outside paper-only. Track as a follow-up for Prompt 5 or 6: add `scripts/dev-up.sh` (or `make dev-up`) that brings up Homebrew Postgres + Redis + a venv-installed FastAPI process with one command. Document in DEFERRED.md.

D2. **Tier 2 staying Full while Part 9 is fully deferred.** REJECT — the existing F2 fix (Part 4 Decision section now reads "Full scope in the May 25 demonstration if all prompts land on schedule; reclassified to post-sprint roadmap in the fallback case") already addresses the underlying contradiction. The remaining concern is about *whether Part 4 will actually land*, which is a schedule risk, not a document inconsistency. Owned in the Schedule risk paragraph of ADR Consequences.

D3. **"All five present in UI" and "dashboard wired to the real API" are integration commitments, not presentation notes.** ACCEPT — soften the wording in this PR. Change ADR 0025 Part 6 bullet "All five present in UI" → "All five named and described in the UI; the three pre-generated agents render archived output". Change Part 8 bullet "per-institution dashboard wired to the real API" → "per-institution dashboard rendering data from the real API for at least one named institution". Mirror both in PLAN.md May 25 scope subsections.

D4. **Precedent basis is not complete.** ACCEPT — already addressed by Proposed status and explicit "no sprint-phasing comparator located" disclaimer in the Precedent section. No further action needed.

**Risks not flagged elsewhere (7):**

R1. **Authority confusion between PLAN/ADR/execution tracker.** DEFER — overlaps with finding 1, same follow-up scope.

R2. **Named-audience-list rot.** ACCEPT — fix tonight by collapsing audience prose in ADR Context and PLAN.md top section to stable class labels ("SBS technical and policy reviewers" + "WBG delivery team"), with named attendees kept in meeting notes.

R3. **"Full/Reduced/Deferred" not tied to test evidence.** DEFER — same as finding 2.

R4. **Pre-generated agent provenance risk (Part 6).** ACCEPT — tighten Part 6 bullet to add: "The three pre-generated agents render output that is generated by the same agent code path running against curated synthetic complaints in advance, not hand-written prose; the demonstration can show the generation command and the output file together." Apply to both ADR 0025 and PLAN.md Part 6 May 25 scope subsection.

R5. **"Published" overclaim for v0.1 standards pack.** Duplicate of finding 3 — handled.

R6. **Schedule compression hidden in "closed prompts."** DEFER — accepted as a real readability risk for a future reader. Document in DEFERRED.md as a note: PLAN.md "13-prompt sequence" lists prompts but does not name calendar dates; future PLAN.md hygiene pass should add a one-column "date landed / target date" to the prompt list.

R7. **Fallback doesn't restate the minimum observable chain (audit log, trace).** ACCEPT — fix tonight by adding to ADR 0025 Schedule risk paragraph the existing minimum observable chain language from the Vertical Slice Target ("A signed mTLS request to POST /v1/complaints → validated against Annex 1-A → persisted → event emitted → audit log → trace in Grafana"). Make this the explicit minimum bar that survives the Prompts 5-8 fallback.

**Recommended actions (8):**
Most map to the dispositioned findings above. The two that don't:

RA-7. **Add Tier 2 cut line.** ACCEPT — add to PLAN.md Part 4 May 25 scope subsection: "Cut line if Tier 2 slips: ship Tier 1 only with an explicit 'Tier 2 batch deferred to post-sprint' card in the demo deck." Mirror in ADR 0025 Part 4 bullet.

RA-8. **Explicit demo truthfulness rules.** DEFER — important but operational/process, not document content. Owned by the maintainer in pre-demo prep, not the ADR. Note in session journal.
