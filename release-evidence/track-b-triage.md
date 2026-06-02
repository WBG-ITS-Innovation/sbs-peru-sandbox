# Track B — Step 1: Agent-Layer Salvage Triage

**Mode:** strictly read-only. No tracked file other than this report was created or modified.
**Branch under inspection:** `origin/part-12/agent-layer` (parked, drafted as PR #53)
**Baseline:** `origin/main` (post-scrub, post-PR #54)
**Locked architecture:** conduct supervision only · 5 agents (3 real Triage / Investigation / Cockpit + 2 scaffolded) · 3 personas (supervisor, analyst, unit-head)
**Generated:** 2026-06-02 by Claude Code, working directory `WBG-ITS-Innovation/sbs-peru-sandbox`

---

## 1. Candidate-commit enumeration

Total commits in `main..part-12/agent-layer`: **17** (16 non-merge + 1 merge).
Source: `git log --oneline --no-merges origin/main..origin/part-12/agent-layer` and `… --merges …`.

Linear (oldest → newest, as the branch was built):

| # | SHA       | Subject                                                                                            |
|---|-----------|----------------------------------------------------------------------------------------------------|
| 1 | `cb0e9d1` | feat(p10.7): polish pilot UI previews                                                              |
| 2 | `a0ca47c` | feat(p11a): wire live ingestion with redaction and data quality                                    |
| 3 | `834d6e7` | feat(p11): add institution sandbox ingestion client                                                |
| – | `3ad0efa` | **merge:** P11 sandbox completion (P11A + P11A.5a) — parents `b172706` (in main) + `834d6e7`       |
| 4 | `8f28b5a` | feat(p11): close P11 sandbox — RUC redaction, blocker fixes, walkthrough                           |
| 5 | `4a5b0e1` | feat(p11): Annex 1-A 27-field DQ validator (DQ-A1A-007..027)                                       |
| 6 | `57f0d4b` | docs(p11): browser walk evidence — sandbox close verified                                          |
| 7 | `eecfdd1` | feat(p11): demo-ready overlay — real SBS Annex 1-A sample ingestion                                |
| 8 | `667b28f` | feat(p11): demo-ui-polish overlay — taxonomy panel, tier badges, unknown-term flag                 |
| 9 | `3f4b5c8` | feat(p12): agent layer — 3 real agents, 2 scaffolded, 10 tools, provider-pluggable                 |
|10 | `fcecb44` | feat(demo): complaint journey demo overlay for 2026-05-27 SBS demo                                 |
|11 | `b6406db` | feat(demo): coherent complaint journey + agents + docs + assistant for 2026-05-27                  |
|12 | `86b287e` | feat(demo): live ingestion + per-complaint processing + RR1 workbench                              |
|13 | `6e7220f` | feat(demo): SUCAVE cockpit, thorough processing, HITL controls, docs deepen                        |
|14 | `84319dc` | feat(reshape): cockpit reshape P-RESHAPE-1..9 — agents, personas, contract v0.2.0                  |
|15 | `ae74ab1` | fix(ci): parameterize standards-pack version in validate workflow                                  |
|16 | `d90c4b4` | P-RESHAPE-10: Frontend pass — 5 persona dashboards + agent cards + chatbot                         |

**Series-1 / 1b scrub commits in the delta:** none. The scrub commits (`638061c chore(series-1)`, `62a4134 chore(series-1b)`) landed on `main` *after* the part-12 branch tip, so they appear in `main`-only and never in this delta. The "exclude scrub commits by subject" rule from the brief therefore has nothing to exclude here.

---

## 2. Per-commit triage table

Columns: **Class** ∈ {KEEP, CUT, FLAG, ALREADY-IN-MAIN}. **Old-names** = grep hits across the diff for the set `maria|lucía|jorge|fisnik|antoine|mariela|sergio|allain|cañote|veronica|diego|patricia|roberto|jtaquia|compliance-ai-kg|wbg-ca-bundle|pa-wbg-decrypt|sbs\.gob\.pe`. **Real-data** = adds or commits non-synthetic SBS data, or commits fixtures derived from it.

| SHA       | Files touched | Class            | Old-names hits | Real-data | Rationale |
|-----------|--------------:|------------------|---------------:|-----------|-----------|
| `cb0e9d1` | 24            | **ALREADY-IN-MAIN** | n/a         | none      | Same `git patch-id` (`ec2dccd5…`) as main's `b172706`. Identical content already merged via the rebase that produced current main. Skip. |
| `a0ca47c` | 30            | **KEEP**         | 2              | none      | P11A live-ingestion endpoint + deterministic-redaction engine + data-quality contract + ADR 0044 / 0045. Foundation for every downstream KEEP. |
| `834d6e7` | 7             | **KEEP**         | 2              | none      | P11A.5a sandbox granular endpoint + institution-side CLI sender. The FI submission path the prototype actually demos. |
| `3ad0efa` | merge         | **ALREADY-IN-MAIN (no separate pick)** | – | – | Parents = `b172706` (in main) + `834d6e7` (already a linear KEEP). `git log a0ca47c..3ad0efa^2` confirms the second parent's unique commits are `a0ca47c`, `834d6e7`, `cb0e9d1` — all already covered by the linear KEEP set. **Do NOT `git cherry-pick -m 1 3ad0efa`.** Linear picks below replicate the merge content without bringing in the merge-resolution noise. |
| `8f28b5a` | 15            | **KEEP**         | 3              | none      | RUC redaction (`pii_ruc` kind in deterministic engine), monkeypatch leak fix, demo.sh uv-fallback, three i18n literals translated. References "Lucía/Sergio/Mariela" in walkthrough doc — flagged for re-scrub. |
| `4a5b0e1` | 24            | **KEEP**         | 4              | none*     | Closes the DQ scope-cut from `8f28b5a`: 21 new Annex 1-A rules, 9 code-list YAMLs, 51 unit tests, additive audit emissions. *Commits `annexo.pdf` (342 KB) — verify this is the public Res. SBS 04036-2022 reglamento (which is public), not internal SBS material, before cherry-pick. |
| `57f0d4b` | 1             | **KEEP**         | 0              | none      | Thirteen-line docs-only follow-up to `8f28b5a` recording manual browser walk. Trivial. |
| `eecfdd1` | 28            | **FLAG**         | 0              | indirect — see below | Adds `taxonomy/dictionary_v1.py` (clean keeper), the `20260526_0001_p11_demo_ready_columns` migration (5 nullable resolution columns + 1 raw column — clean keeper), the `taxonomy-normalized` orchestrator step and `flag_unknown_taxonomy` plumbing (clean keeper), CORS middleware + `0.0.0.0` Next dev binding (clean keeper), and `scripts/ingest_sample_dataset.py` (598 lines) which **reads `data/sbs_sample/SAMPLE_MUESTRA_ENTITY_CLAIMS.xlsx` at runtime**. The xlsx itself is **not committed** — the same commit adds `data/sbs_sample/` to `.gitignore` and the operator places the file locally. Also adds 4 demo docs (`2026-05-27-demo-ready.md`, `2026-05-27-narration-anchors.md`, `2026-05-27-two-laptop-setup.md`, plus an addendum to `2026-05-26-p11-sandbox-close.md`). **Human decision:** keep the architecture-side pieces (taxonomy dict, migration, orchestrator step, CORS) as one tight commit and carve out `scripts/ingest_sample_dataset.py` + the four demo docs into a second commit the human can include or drop based on whether the real-data dependency is acceptable for the salvage branch. |
| `667b28f` | 21            | **KEEP**         | 1              | none      | `flag_unknown_taxonomy` migration + endpoint `/v1/internal/cockpit/taxonomy-stats`, `TaxonomyPanel.tsx`, `TaxonomyStatsTile.tsx`, tier-1 / tier-2 badge variants (WBG cyan / WBG gold), resolution-status sub-panel. Two new tests; depends on `eecfdd1`. |
| `3f4b5c8` | 67            | **KEEP**         | 17             | none      | **The Part 12 keystone.** Adds Triage / Investigation / Synthesis (3 real) + Taxonomy Harmonizer / Cross-Source Correlator (2 scaffolded via `ReplayProvider` fixtures) + 10 tools. `ModelProvider` protocol with `on_prem` (vLLM with mock fallback), `replay`, `mock`, and `cloud` (gated `NotImplementedError`) implementations. ADR 0001 supersedes the original MCP+A2A+LangGraph proposal in favour of an in-house tool-calling loop. 26 new tests, BCO-2026-000001 invariants asserted. Matches the locked 5-agent (3+2) architecture exactly. Old-names hits are in replay fixtures (`_default.json`, `BCO-2026-000001.json`), agent docstrings, and the prompt-14 session journal: "Lucía", "Sergio", "Mariela", "María", "Diego". **Re-scrub will need to rewrite those to role nouns (supervisor / superintendent / supervisor lead / analyst) — same approach as Series 1.** |
| `fcecb44` | 18            | **FLAG**         | 1              | **YES** — fixture file `app/src/lib/journey-emails.json` (662 lines) carries 20 real SBS complaint records from the sample xlsx with `<PERSON>` / `<PE_DNI>` / `<NUMBERS>` / `<ORGANIZATION>` / `<LOCATION>` placeholders. The narrative bodies, monetary amounts, branch identifiers, and resolution descriptions are **real, not synthetic**. Also adds `scripts/journey_submit.py` and `scripts/demo_load_sbs_sample.py`. | New `/app/demo-journey` route, the FI-side auth-chain visualisation, two new Next proxy routes. **Demo overlay, not architecture.** The auth-chain visualisation has onboarding value (shows mTLS thumbprint, OAuth scope, HMAC prefix, Idempotency-Key, complaint_id) but is welded to the journey-emails fixture. **Human decision:** include the route + script and replace the fixture with a fully synthetic equivalent, or drop the whole journey overlay. |
| `b6406db` | 29            | **FLAG**         | 10             | **YES** — extends real-data fixture and adds `scripts/seed_golden_complaint.py` keyed to BCO-2026-000001 demo invariants. | Five-in-one demo bundle: golden-complaint seeding script, the `/app/fi/banco-demo-001/*` FI app (inbox / triage / submit), an updated `/app/demo-journey` with three live agents seeded per submission, Recharts cockpit charts, `/app/assistant` wired to Azure OpenAI via `scripts/assistant_query.py`, and `/app/docs` hub (4 tabs: arquitectura, API, Anexo 1-A model, agents). Some pieces (the assistant wiring through the WBG ITS tenancy, the docs hub) are arguably onboarding artifacts; the FI route and golden-seeding script are demo-coupled. **Human decision:** salvage the assistant scripts + docs hub separately, or take none of it. |
| `86b287e` | 19            | **FLAG**         | **49**         | **YES (committed)** — adds `app/src/lib/rr1-2025.json` (2961 lines) derived from `data/sbs_sample/Copy of RR1_2025_values.xlsx`. The JSON carries real RR1 2025 monthly figures by institution × month for Empresa / Producto / Motivo sheets. RR1 reports are public regulatory artifacts but the file is still **direct real SBS data committed to the repo**. Also expands `journey-emails.json` from 662 → 2064 lines (more real complaint narratives). The commit message also states the FI inbox now shows **"raw deterministic-fake PII"** (real-looking names, DNIs, phones, emails) instead of `<PERSON>` placeholders. | `/app/ingestion` theatre, `/app/processing` drilldown with right-rail activity log, `/app/rr1` SUCAVE-style replica with chart builder, Radix tooltips on cockpit charts. **Demo-only. The RR1 fixture is the largest single real-data exposure in the candidate set.** **Human decision:** strong recommendation to CUT this commit unless someone signs off on committing aggregated RR1 figures (and reviews whether the deterministic-fake PII is actually deterministic-fake or real-looking-but-distinct). |
| `6e7220f` | 9             | **FLAG**         | 22             | indirect  | Pure UI polish on top of `86b287e`: `InsightsBoard` with 6 aggregates and 4 KPI tiles, much-deepened processing drilldown, HITL toast-only controls on every pipeline + agent stage, three new doc-hub tabs (Sandbox técnico / Ciclo de vida / Agentes y herramientas master-detail). Approvals page becomes supervisor read-only with banner. No backend touched. Heavy use of "Lucía" / "Jorge" persona names in UI copy. **Human decision:** the HITL pattern and the documentation deepens have salvage value; the persona names and `/app/rr1` dependence weld it to `86b287e`. |
| `84319dc` | ~150          | **CUT**          | **199**        | none directly | **Pure RESHAPE.** Six-agent registry (`AGENT_REGISTRY`) with **DIValeVale**, **Reclamito**, and **Lupaman** (the last is described in code as "a UX-only composite of Peer Risk Radar + Sector Broadcast") alongside Triage / Investigation / Insight Chatbot. Five persona scopes with the renames `mariela→jorge`, `patricia→rosa`. Introduces Peer Risk Radar, Issue Resurface (`api/sbs_api/agents/issue_resurface.py`), Sector Broadcast (`api/sbs_api/agents/sector_broadcast.py`), social ingestion + `FRAUD_EMERGENCE`, DIValeVale (`api/sbs_api/agents/divalevale/`), Insight Chatbot (`api/sbs_api/agents/insight_chatbot.py` + scope/limits/suggestions/tools), aggregation tick (`api/sbs_api/aggregation/{detector,severity,tick,windower}.py`), nine new Alembic migrations `20260528_0001..0009`, OpenAPI contract bump v0.2.0 with `SupervisoryMetadata` on `ComplaintListItem`. **Deletes the keeper-scaffold files added by `3f4b5c8`** — `api/sbs_api/agents/taxonomy_harmonizer.py`, `api/sbs_api/agents/cross_source_correlator.py`, and their replay fixtures. **Carries a failing CI check per the brief**; `gh` is not installed on this machine so the specific check name cannot be retrieved here — confirm via GitHub UI before any decision that depends on this commit (which won't happen since it is CUT). Touches every axis the locked architecture forbids: 6 agents > 5, 5 personas > 3, fraud emergence, sector broadcast, whimsical agent codenames. |
| `ae74ab1` | 6             | **KEEP**         | 0              | none      | Clean CI fix. `standards-pack/` and the `standards-pack-validate.yml` workflow both exist in current `main` (verified via `git ls-tree main -- .github/workflows/standards-pack-validate.yml` and `git ls-tree main -- standards-pack/`). The fix reads `PACK_VERSION` from `standards-pack/manifest.json` so a future version bump won't break the workflow. One new test (`tests/test_ci_workflow_parameterized.py`). Order-independent of the agent/p11 keepers. |
| `d90c4b4` | 21            | **CUT**          | 18             | none      | RESHAPE frontend matched to the `84319dc` backend. Five persona dashboards (`AnalystDashboard`, `SbsItDashboard`, `SuperintendentDashboard`, `SupervisorDashboard`, `UnitHeadDashboard`) for personas **Lucía, María, Jorge, Sergio, Rosa**. `AgentCard`, `ActionButton`, `Explanation`, `TaskInbox/Outbox`, `InsightChatbotPanel`, `PersonaPicker`. Persona cookie + `X-SBS-Role` BFF pattern. Depends entirely on `84319dc`'s backend; cannot stand alone. |

*Old-names hits and real-data flags above are derived from `git show <sha>` piped through grep against the patterns named in the brief. Hit counts include both code and prose (docs, fixtures, session journals), so the absolute number is less meaningful than the relative concentration — `84319dc` 199 hits is genuinely RESHAPE-saturated, `3f4b5c8` 17 hits is mainly fixture+docstring references that the re-scrub will rename.*

---

## 3. Merge-commit handling

`3ad0efa merge: P11 sandbox completion (P11A + P11A.5a)`
Parents:
- `b172706` — `feat(p10.7): polish pilot UI previews` (in current main)
- `834d6e7` — `feat(p11): add institution sandbox ingestion client` (in the KEEP set)

`git log --oneline 3ad0efa^1..3ad0efa^2` returns `834d6e7`, `a0ca47c`, `cb0e9d1`. All three are already covered by the linear KEEP set (with `cb0e9d1` skipped as ALREADY-IN-MAIN).

**Recommendation: do NOT run `git cherry-pick -m 1 3ad0efa`.** Cherry-pick `a0ca47c` and `834d6e7` linearly. The merge's own diff is purely conflict-resolution noise from layering P11A on the p10.7 polish — content already produced by the post-scrub main.

---

## 4. Proposed cherry-pick order for the KEEP set

Parents-before-children, original branch order preserved:

| Pick # | SHA       | Subject                                                                  |
|-------:|-----------|--------------------------------------------------------------------------|
| 1      | `a0ca47c` | feat(p11a): wire live ingestion with redaction and data quality          |
| 2      | `834d6e7` | feat(p11): add institution sandbox ingestion client                      |
| 3      | `8f28b5a` | feat(p11): close P11 sandbox — RUC redaction, blocker fixes, walkthrough |
| 4      | `4a5b0e1` | feat(p11): Annex 1-A 27-field DQ validator (DQ-A1A-007..027)             |
| 5      | `57f0d4b` | docs(p11): browser walk evidence — sandbox close verified                |
| 6      | `667b28f` | feat(p11): demo-ui-polish overlay — taxonomy panel, tier badges          |
| 7      | `3f4b5c8` | feat(p12): agent layer — 3 real agents, 2 scaffolded, 10 tools           |
| 8      | `ae74ab1` | fix(ci): parameterize standards-pack version in validate workflow        |

Notes on ordering:
- `ae74ab1` is independent of the p11/p12 stack; placed last so a re-scrub pass over the keepers doesn't have to step around it. Could equally go first.
- `667b28f` depends on `eecfdd1` (FLAG, see below) for the `flag_unknown_taxonomy` column source. If `eecfdd1` is dropped or carved up, pick #6 needs the matching pieces (`taxonomy/dictionary_v1.py`, `taxonomy-normalized` orchestrator step, the `20260526_0001` migration) added inline. **The proposed pick order assumes the architecture-side pieces of `eecfdd1` are included as pick #5.5.**
- Skipped from the linear branch: `cb0e9d1` (already in main by content), `3ad0efa` (merge content already captured by `a0ca47c` + `834d6e7`).

### CUT (do not cherry-pick)

| SHA       | Subject                                                                  |
|-----------|--------------------------------------------------------------------------|
| `84319dc` | feat(reshape): cockpit reshape P-RESHAPE-1..9                            |
| `d90c4b4` | P-RESHAPE-10: Frontend pass — 5 persona dashboards + chatbot             |

### FLAG (human decision required before pick)

| SHA       | Subject                                                                  | What the human must decide |
|-----------|--------------------------------------------------------------------------|---------------------------|
| `eecfdd1` | feat(p11): demo-ready overlay — real SBS Annex 1-A sample ingestion      | Take the whole commit (includes `scripts/ingest_sample_dataset.py` + 4 demo docs referring to a real-data path even though the xlsx itself is `.gitignore`d), or carve into (a) architecture-side pieces (taxonomy dict + migration + orchestrator step + CORS — clean keeper) and (b) demo-data wiring (script + docs — optional). |
| `fcecb44` | feat(demo): complaint journey demo overlay                               | The `journey-emails.json` fixture is real complaint data with redaction-token placeholders, not synthetic. Drop the whole commit, or salvage `/app/demo-journey` + `scripts/journey_submit.py` and substitute a fully synthetic fixture. |
| `b6406db` | feat(demo): coherent complaint journey + agents + docs + assistant       | Two pieces have onboarding value (the `/app/docs` hub and the Azure OpenAI assistant wiring through the existing WBG ITS tenancy). The FI app and golden-seeding script are demo-coupled. Take selectively or drop entirely. |
| `86b287e` | feat(demo): live ingestion + per-complaint processing + RR1 workbench    | Commits `rr1-2025.json` (real aggregated RR1 2025 institution-by-month figures) and expands `journey-emails.json` to 2064 lines of real complaint data. Commit message also claims the FI inbox shows "raw deterministic-fake PII" — verify this is actually synthetic before any partial salvage. Strong recommendation: CUT. |
| `6e7220f` | feat(demo): SUCAVE cockpit, thorough processing, HITL controls           | Pure UI polish; no backend touched. The HITL pattern and docs-hub deepens have salvage value but the commit is welded to `/app/rr1` (from `86b287e`) and uses "Lucía / Jorge" persona names heavily. Treat as a follow-on candidate only if `86b287e` is taken. |

---

## 5. Conflict hot-spots (KEEP set ∩ post-scrub main)

Computed as `comm -12` between `git show --name-only` on the two scrub commits (`638061c`, `62a4134`) and the union of files touched by the eight KEEP commits.

| File                                       | Why it conflicts |
|--------------------------------------------|------------------|
| `.env.example`                             | Scrub rewrote env keys + descriptions; `a0ca47c` and `3f4b5c8` add new agent-pipeline / live-ingestion env vars. |
| `.gitignore`                               | Scrub added secret-scan ignores; `eecfdd1` adds `data/sbs_sample/` ignore. |
| `api/sbs_api/findings/builder.py`          | Scrub updated audit / persona docstrings; `a0ca47c`, `eecfdd1`, `667b28f`, `3f4b5c8` all extend the findings builder. **High-conflict file.** |
| `app/src/components/ui/Badge.tsx`          | Scrub adjusted persona-name strings; `667b28f` adds `tier1`/`tier2`/`warning` variants. |
| `app/src/i18n/en.json`                     | Scrub rewrote persona / supervisor strings; almost every KEEP commit adds new i18n keys. **High-conflict file.** |
| `app/src/i18n/es.json`                     | Same as above. **High-conflict file.** |
| `docs/PLAN.md`                             | Scrub updated PLAN to reflect Series 1 close; `a0ca47c`, `eecfdd1`, `3f4b5c8` all amend PLAN sections. **Hand-edit on each pick.** |
| `docs/adr/README.md`                       | Scrub renamed ADR titles; `a0ca47c` adds ADR 0044/0045, `3f4b5c8` supersedes ADR 0001. |
| `tests/test_internal_audit.py`             | Scrub rewrote audit docstrings; `8f28b5a` changes the `monkeypatch.delenv` → `monkeypatch.setenv("", …)` pattern in this file. |

**Out-of-set hot-spots to watch on a Keycloak realm pass:** the scrub modified `infra/keycloak/realm-sbs-demo.json` but no KEEP commit touches it directly — the conflict is by contract (persona scopes) rather than file. If a future re-scrub pass renames personas in the realm, KEEP-commit code that reads role claims will need a matching change.

---

## 6. CI status notes

The brief states `84319dc` carries a failing check. `gh` is not installed in this working environment (`(eval): command not found: gh`), so the specific check name and failure message could not be pulled. Confirm via `https://github.com/WBG-ITS-Innovation/sbs-peru-sandbox/commit/84319dc` before any decision that depends on knowing the exact failure — but since the recommendation here is to CUT `84319dc`, this is informational only. All commits in the KEEP set predate `84319dc` and are not implicated in its failure.

---

## 7. Re-scrub scope for the KEEP set

A re-scrub pass over the eight KEEP commits will need to rename Spanish first-names and collaborator references to role nouns. By commit:

| SHA       | Old-name hits | Where they live                                                          |
|-----------|--------------:|--------------------------------------------------------------------------|
| `a0ca47c` | 2             | comments in `tests/integration/test_no_raw_pii_egress.py`, one ADR draft |
| `834d6e7` | 2             | `docs/demo/institution-api-workflow.md`                                  |
| `8f28b5a` | 3             | `docs/demo/2026-05-26-p11-sandbox-close.md`                              |
| `4a5b0e1` | 4             | `docs/demo/2026-05-27-p11-dq-complete.md`                                |
| `57f0d4b` | 0             | —                                                                        |
| `667b28f` | 1             | `docs/demo/2026-05-27-ui-polish.md`                                      |
| `3f4b5c8` | 17            | replay fixtures (`_default.json`, `BCO-2026-000001.json`), agent docstrings (`investigation.py`, `synthesis.py`, `triage.py`), tool descriptions (`narrative.py`), `docs/demo/2026-05-27-agents-ready.md`, `docs/sessions/2026-05-27-prompt-14-agent-layer.md` |
| `ae74ab1` | 0             | —                                                                        |

The pattern matches Series 1 / 1b: replace given names with role nouns (`Supervisor`, `Superintendent`, `Supervisor Lead`, `Analyst`, `Unit Head`) and remove `@worldbankgroup.org` / `@sbs.gob.pe` email references. No structural code change required.

---

## Done

This report is the only file written by this triage. No commit was cherry-picked, no branch was created, no remote was pushed, no working-tree file other than this report was modified.
