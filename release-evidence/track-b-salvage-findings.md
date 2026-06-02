# Track B — Agent-Layer Salvage Findings

**Branch:** `part-14/agent-layer-salvage`
**Off:** `main @ f7c9081` (post-Series-1/1b scrub)
**Mode:** unattended single-session salvage (Step 2 of the Track B brief).
**Final state:** all 7 gates green, **nothing pushed, no PR opened, no merge to main.**
**Generated:** 2026-06-02

---

## 1. Cherry-pick log

Order is parents-before-children, matching the original part-12 branch order. The merge commit `3ad0efa` was NOT picked — its constituent linear commits (`a0ca47c`, `834d6e7`) cover the same content. `cb0e9d1` was skipped (ALREADY-IN-MAIN by patch-id).

| # | Source SHA | Salvage SHA | Subject | Conflicts | Backstop verdict |
|---|---|---|---|---|---|
| 1 | `a0ca47c` | `947323d` | feat(p11a): wire live ingestion with redaction and data quality | i18n + PLAN + ADR README auto-merge | scrub-only deltas (8 i18n + 5 PLAN + 1 ADR lines) |
| 2 | `834d6e7` | `cd2c98b` | feat(p11): add institution sandbox ingestion client | none | clean |
| 3 | `8f28b5a` | `13055b8` | feat(p11): close P11 sandbox — RUC redaction, blocker fixes, walkthrough | i18n + test_internal_audit auto-merge | scrub-only deltas (8 i18n + 5 test actor_id lines) |
| 4 | `4a5b0e1` | `11ac53b` | feat(p11): Annex 1-A 27-field DQ validator | none | clean (annexo.pdf landed; dropped in next commit) |
| 4b | — | `5927202` | chore(p11): drop annexo.pdf pending provenance verification | — | PDF default-EXCLUDE per brief; see §2 |
| 5 | `57f0d4b` | `e700981` | docs(p11): browser walk evidence — sandbox close verified | none | clean |
| 6 | `eecfdd1` | `5b0a8e7` | feat(p11): taxonomy dictionary + DQ columns + CORS (architecture only; demo-data wiring dropped) | .gitignore content conflict resolved by keeping main's verbatim entry | carved per default-drop; see §3 |
| 7 | `667b28f` | `5493fc3` | feat(p11): demo-ui-polish overlay — taxonomy panel, tier badges, unknown-term flag | i18n + Badge + findings/builder auto-merge | scrub-only deltas (8 i18n + 1 builder comment + 1 Badge comment) |
| 8 | `3f4b5c8` | `d12422e` | feat(p12): agent layer — 3 real agents, 2 scaffolded, 10 tools, provider-pluggable | `.env.example` content conflict (merged; main's comprehensive form + new Part 12 vars), `docs/demo/2026-05-27-narration-anchors.md` modify-vs-delete (kept delete from carve) | scrub-only deltas (19 .env comment lines + 5 PLAN + 1 ADR + 1 builder comment + 8 i18n) |
| 9 | `ae74ab1` | `1ffc104` | fix(ci): parameterize standards-pack version in validate workflow | README + build-standards-pack.sh auto-merge | deltas explained: 19 README lines were RESHAPE content from CUT `84319dc` + CORS block from dropped eecfdd1; 4 build-script lines were a parallel 0.1→0.2 version bump that didn't survive auto-merge (kept main's 0.1.0 — the whole point of the parameterization is that the literal version no longer breaks CI) |
| 10 | — | `a259c88` | chore(series-1c): re-scrub salvaged agent layer | — | applies Series-1/1b name→role mapping; see §4 |

**Final branch HEAD:** `a259c88`.
**Commits ahead of main:** 11.

Per-pick completeness deltas live in `release-evidence/conflicts/<sha>/<path>.delta`. Every delta was inspected; all were scrub-rewrite differences (main's already-scrubbed persona copy vs the source commit's pre-scrub copy). No functional code was dropped in any conflict resolution.

---

## 2. The `annexo.pdf` decision

The brief's safe default is EXCLUDE. The unattended salvage agent could not extract PDF text (no `pdftotext` / `PyPDF2` installed locally), so the concrete check defined in the brief — text contains both "Resolución SBS" and "04036-2022" — could not run.

**Dependency analysis (no test breakage):** the only references to `annexo.pdf` are:
- `api/sbs_api/dq/codelists/__init__.py:4` — docstring comment (`"typically ``annexo.pdf``"`). Not a runtime load.
- `docs/demo/2026-05-27-p11-dq-complete.md` — page-number citations. Not a runtime load.

No `.py` test imports, opens, parses, or otherwise reads the PDF. Gate 5 is not at risk.

**Action:** `git rm annexo.pdf` in commit `5927202`; path added to `.gitignore`; human follow-up logged at `release-evidence/track-b-salvage-TODO.md#TODO-1`.

---

## 3. The `eecfdd1` carve

The default-drop rule was applied: KEEP only the four architecture pieces named in the brief; DROP everything else.

**Kept (20 paths, 852 insertions, 28 deletions in commit `5b0a8e7`):**
- `api/sbs_api/taxonomy/__init__.py`, `taxonomy/dictionary_v1.py` (canonical dict for canal / producto / motivo / estado_reclamo / tipo_resolucion)
- `api/migrations/versions/20260526_0001_p11_demo_ready_columns.py` (5 nullable resolution-side columns + 1 raw column)
- `api/sbs_api/demo_ingestion/orchestrator.py` (the `taxonomy-normalized` step between schema-validated and pii-redacted; audit chain grows 5→6; `flag_unknown_taxonomy` plumbing)
- `api/sbs_api/app.py` (CORS middleware via `SBS_API_CORS_ALLOW_ORIGINS`)
- `app/package.json` (Next.js dev/start bind `0.0.0.0:3000`)
- `api/sbs_api/db/models/{complaint,raw_complaint}.py` (matching ORM fields)
- `api/sbs_api/models/demo_ingestion.py` (10 optional Annex 1-A request fields)
- `api/sbs_api/findings/builder.py` (surfaces the 5 new columns)
- `app/src/app/(supervisor)/findings/[id]/page.tsx`, `app/src/types/findings.ts`, `app/src/i18n/{en,es}.json` (UI surfacing of the new columns)
- `api/sbs_api/routes/{internal,sandbox_complaints}.py` (response plumbing for taxonomy_normalizations + flag)
- `api/sbs_api/config.py` (CORS env var)
- `docs/PLAN.md` (one-line update: audit chain grows 5→6)
- `tests/integration/test_live_ingestion_endpoint.py`, `tests/test_alembic_migration.py` (test updates for the new behaviour)

**Dropped:**
- `scripts/ingest_sample_dataset.py` (598-line script that reads `data/sbs_sample/SAMPLE_MUESTRA_ENTITY_CLAIMS.xlsx` at runtime — the demo-data wiring)
- `docs/demo/2026-05-27-demo-ready.md`, `docs/demo/2026-05-27-narration-anchors.md`, `docs/demo/2026-05-27-two-laptop-setup.md` (three new demo docs)
- `docs/demo/2026-05-26-p11-sandbox-close.md` addendum (revert to state as of `8f28b5a`)
- `docs/demo/2026-05-27-p11-dq-complete.md` addendum (revert to state as of `4a5b0e1`)
- `README.md` addition (referenced the dropped two-laptop doc)
- `.gitignore` `data/sbs_sample/` entry (already in main from Series 1; kept main's wording verbatim)

Each dropped path was `git rm`'d from both index and disk per the brief's mechanical requirement, so a subsequent `git add -A` cannot re-sweep it.

---

## 4. Re-scrub scope and the string-keyed-fixture rule

The Series-1c re-scrub (commit `a259c88`) applied the Series-1/1b name→role mapping to the salvaged tree.

### Mapping applied

| Old name | Replacement (English) | Replacement (Spanish) |
|---|---|---|
| María / Maria | Supervisor / supervisor | Supervisora / supervisora |
| Lucía / Lucia | Analyst / analyst | Analista / analista |
| Sergio | Superintendent / superintendent | Superintendente / superintendente |
| Mariela | Supervisor lead | jefa de supervisión |
| Diego / Luis-and-Diego | analyst (role placeholder) / "SBS taxonomy reviewers" | — |
| antoine (test actor_id fixture) | "test-operator" | — |

### Files scrubbed

| File | Hit type | Replacement |
|---|---|---|
| `api/sbs_api/agents/fixtures/replay/synthesis/BCO-2026-000001.json` | `notes` field + `text` turn | role nouns |
| `api/sbs_api/agents/tools/narrative.py` | module docstring + 1 comment + `SummarizeForExecutiveTool.description` | role nouns |
| `api/sbs_api/dq/codelists/__init__.py` | docstring | "SBS taxonomy reviewers" |
| `api/sbs_api/dq/codelists/moneda.yaml`, `tipo_documento.yaml` | review_status comment | "SBS taxonomy reviewers" |
| `api/sbs_api/redaction/policy.py` | `DEMO_KNOWN_NAMES` allowlist values | rotated "María Velásquez" → "Andrés Cabrera" (kept name-shaped; allowlist needs name strings to function) |
| `app/src/components/findings/ExecutiveBriefPanel.tsx` | 1 file comment | role nouns |
| `docs/adr/0001-three-layer-mcp-a2a-langgraph.md` | 4 prose lines | role nouns |
| `docs/demo/2026-05-26-p11-sandbox-close.md` | 3 prose lines (scope, edit gap, persona switcher chain) | role nouns |
| `docs/demo/2026-05-27-p11-dq-complete.md` | 1 codelist-sign-off line | "SBS taxonomy reviewers" |
| `scripts/institution_push_demo.py` | `_NAME_TOKENS` PII fixture | rotated "María Pérez Quispe" → "Andrés Cabrera Núñez" (same rationale as redaction policy) |
| `tests/integration/test_audit_and_sse_completeness.py`, `tests/test_persona_switch_audit_contract.py` | `actor_id="antoine"` fixtures (6 occurrences) | `"test-operator"` |

### String-keyed-fixture matched-pair audit

The brief requires: if a fixture value carries a name and agent code matches on that string, scrub both sides atomically OR leave both. The audit grep:

```
grep -rE '["\047](Sergio|Lucía|Lucia|Mariela|Diego|Patricia|Roberto)["\047]'
  api/sbs_api/agents/  api/sbs_api/findings/  api/sbs_api/demo_ingestion/
  (excluding fixtures/replay)
```

returned **no matches**. Additional check for `== 'Sergio'` / `.startswith('Lucía')` style returned **no matches**. No fixture value was matched on by code. **No string-key was flagged not-scrubbed.**

### CODEOWNERS placeholders

`.github/CODEOWNERS` carries 5 hits against the regex (`@<antoine-handle>`, `@<fisnik-handle>`) but these are intentional Series-1 fill-in placeholders, unchanged from main (`git diff main -- .github/CODEOWNERS` is empty). The Gate 3 verdict excludes them.

---

## 5. Gate results

| # | Gate | Result | Detail |
|---|---|---|---|
| 1 | `gitleaks --no-git` over committable scope | **PASS** | 13 findings in working tree, all filtered out by `git check-ignore` (in `.env*`, `dev-ca/`, `.next/`, `*.bak`, `standards-pack/examples/`). 0 findings in committable scope. |
| 2 | `trufflehog filesystem` | **PASS** | 92 unverified raw findings, 0 verified findings. 0 verified findings in committable scope. |
| 3 | Name-sweep (persona/collaborator regex) | **PASS** | 0 files with hits in committable scope (excluding `release-evidence/` and the unchanged-from-main `.github/CODEOWNERS` placeholders). |
| 4 | Real-data gate | **PASS** | 0 tracked paths matching `sbs_sample|rr1-2025|journey-emails`; `data/sbs_sample/` and `annexo.pdf` both gitignored. |
| 5a | 26 agent tests from `3f4b5c8` (hard count) | **PASS** | 26 passed in 2.97s. |
| 5b | Full pytest suite vs main baseline | **PASS** | Main: 528 passed, **1 failed** (`test_audit_post_returns_404_when_secret_not_configured` — the exact blocker `8f28b5a` fixes), 6 skipped. Salvage branch: **674 passed, 0 failed, 6 skipped.** Zero new failures; the main-baseline failure is resolved by the salvage. |
| 6 | `scripts/demo.sh --scale small` | **PASS** | After restarting the worker + webhook-listener containers (their long-running Python processes had imported the ORM 4 days ago on a different branch, leading to a stale `submotivo` column in INSERTs — purely environmental, not a salvage bug). Final run: `demo.sh: PASS`, all 3 batches `status=complete`, all 3 `listener_pass=true`, exit code 0. |
| 7 | Scaffold survival | **PASS** | `api/sbs_api/agents/taxonomy_harmonizer.py` and `api/sbs_api/agents/cross_source_correlator.py` both present; both wired to `ReplayProvider`; replay fixtures `BCO-2026-000001.json` + `_default.json` present under `api/sbs_api/agents/fixtures/replay/{taxonomy-harmonizer,cross-source-correlator}/`. The deletion in `84319dc` was not inherited. |

### Gate 6 incident note (environmental, not a code bug)

First attempt failed with `ProgrammingError: column "submotivo" of relation "complaints" does not exist` on all 3 batches. Root cause: the `sbs-worker` Docker container had been up for 5 days (`docker compose ps` showed `Up 5 days`). Its long-running Python process imported `complaint.py` from when the host was on the part-13 branch, where the ORM model carried the aggregate-dashboard `submotivo`, `submotivo_2`, `topic` columns added by part-13's `60b563e feat(enrich): post-ingest synthetic enrichment` (migration `20260529_0001`). The salvage branch's ORM does NOT have these columns (correctly — they belong to the CUT aggregate work), and the salvage branch's DB schema does NOT have them either, but the worker process was still emitting INSERTs that listed them. `docker compose restart worker webhook-listener` fixed it: Python reimported the current source from the read-only `:/app:ro` mount.

This is documented here so the human running the post-salvage walk knows to restart long-running compose services after switching branches, especially when crossing the `60b563e` boundary.

---

## 6. Outputs

```
release-evidence/
├── track-b-triage.md                  (Step-1 triage, from session 1)
├── track-b-salvage-findings.md        (this file)
├── track-b-salvage-TODO.md            (human follow-ups)
├── branch-cleanup-audit.md            (Step-5 branch-containment audit)
└── conflicts/
    ├── 3f4b5c8/                       (5 deltas + 1 .env.example.diff)
    ├── 667b28f/                       (4 deltas)
    ├── 8f28b5a/                       (3 deltas)
    ├── a0ca47c/                       (4 deltas)
    └── ae74ab1/                       (2 deltas)
```

Commit log on `part-14/agent-layer-salvage` (ahead-of-main, oldest → newest):

```
947323d  feat(p11a): wire live ingestion with redaction and data quality
cd2c98b  feat(p11): add institution sandbox ingestion client
13055b8  feat(p11): close P11 sandbox — RUC redaction, blocker fixes, walkthrough
11ac53b  feat(p11): Annex 1-A 27-field DQ validator (DQ-A1A-007..027)
5927202  chore(p11): drop annexo.pdf pending provenance verification
e700981  docs(p11): browser walk evidence — sandbox close verified
5b0a8e7  feat(p11): taxonomy dictionary + DQ columns + CORS (architecture only; demo-data wiring dropped)
5493fc3  feat(p11): demo-ui-polish overlay — taxonomy panel, tier badges, unknown-term flag
d12422e  feat(p12): agent layer — 3 real agents, 2 scaffolded, 10 tools, provider-pluggable
1ffc104  fix(ci): parameterize standards-pack version in validate workflow
a259c88  chore(series-1c): re-scrub salvaged agent layer
```

11 commits. Conventional Commits format. Rebase-ready (no merge commits, no squash). **Nothing pushed, no PR opened, no merge to main.** The branch is local-only and waiting for the human's review.

---

## 7. Human next steps (suggested order)

1. Read `release-evidence/track-b-salvage-TODO.md` — three named follow-ups (PDF provenance, eecfdd1 carve intent, PR #53 closeout note).
2. Skim `release-evidence/conflicts/` and inspect any delta the human wants to re-validate.
3. Read this file end-to-end.
4. Read `release-evidence/branch-cleanup-audit.md` and decide on the 7 SAFE-TO-DELETE branches.
5. `git push -u origin part-14/agent-layer-salvage` and `gh pr create` when ready. Do not skip hooks; do not force-push.
6. After merge, run the SAFE-TO-DELETE plan: `git push origin --delete <branch>` per row in the audit table.

---

**Done.** All 7 gates green. The salvage branch is local-only and untouched by push.
