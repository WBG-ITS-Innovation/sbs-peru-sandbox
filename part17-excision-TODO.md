# Part 17 — RESHAPE excision: items left for human review

All exit gates pass (pytest collects with 0 errors; build + tsc clean; cockpit
route intact; gitleaks + name sweep clean; no dangling references). These are
judgment calls and follow-ups for a human.

## Deviations from the prompt's literal REMOVE list
1. **`AggregationStrip`, `AgentCard`, `primitives`** were named as KEEP cockpit
   components in the prompt, but the frontend import graph proves they are
   reachable only from the removed `/dashboard` route and persona dashboards —
   never from `/cockpit/aggregates`. They were removed (per "derive, don't
   assume"). If any was intended for a future cockpit use, restore it from the
   staged deletions. The live cockpit (`AggregatesWorkspace`) does not import them.
2. **`peer_risk/**`** was on the prompt's REMOVE list but is in the KEEP closure
   (the live aggregates route imports `peer_risk.cohorts`; `peer_risk.percentiles`
   computes from `complaints`). It was **kept**. Only the peer-risk agent and the
   `peer_risk_analyses` model/migration were removed. Confirm this is intended.
3. **`auth/persona_scopes.py`** still defines `FI_BRIEF_APPROVE/OVERRIDE` and
   `SECTOR_BROADCAST_APPROVE_*` scope-name constants. They are part of the kept
   persona→scope map and are referenced by the kept `tests/auth/test_scope_enforcement.py`.
   They are permission strings, not imports of removed code, so they are not
   dangling. Decide whether to prune these now-unused scope names from the map
   (would also touch the kept scope-enforcement test).

## Scope expansion beyond the named members
4. The prompt named a narrow backend set (peer_risk_radar, issue_resurface,
   peer_risk_analysis, fi_brief). Removing the `fi_brief`/`peer_risk_analysis`
   models forces removing every file that imports them, which cascades through
   the entire **unmounted** RESHAPE route layer (`ops`, `exec`, `cockpit_tasks`,
   `cockpit_actions`, `agents_divalevale`, `agents_unified`, `chatbot`, `persona`,
   `findings_manual`, `exec_tasking`, `ops_incidents`, `ops_remediation`,
   `sector_broadcast_approvals`) plus the `chatbot`/`sector_broadcast`/`persona_*`
   models and the `aggregation/` tick. All of these were unmounted (never in
   `routes/__init__.py`) and form one connected RESHAPE component disjoint from
   the live app. This matches "you are removing it entirely," but confirm the
   breadth is acceptable.

## Orphaned tables / migrations
5. Migrations `0005_social_and_broadcast`, `0006_chatbot`, `0004_persona_scope`
   (and others) still **create** tables (`sector_broadcasts`, `chatbot_sessions`,
   `persona_tasks`, `persona_audit`, …) whose ORM models were removed. The tables
   are orphaned (no model, no code path) but harmless — the prompt scoped
   migration removal to only the two peer-risk/fi-brief migrations. Decide whether
   to also drop these RESHAPE-table migrations in a later pass (each needs a
   chain re-link).

## Pre-existing / environmental test failures (not caused by the cut)
6. **Run the suite against a fresh, fully-migrated DB + the docker stack** to
   drive the residual failures to green. After the excision: 748 passed, 20
   failed, 18 errors. None are attributable to the cut (see findings gate-2
   analysis). They are:
   - Stale-assertion tests that should be updated or removed:
     `standards_pack/test_v0_2_0_bump` (asserts a 0.2.0 bump not done),
     `standards_pack/test_ci_workflow_parameterized`, and
     `test_alembic_migration::test_baseline_migration_applies_cleanly` (asserts
     the head is `20260527_0001_agents_status`, but the chain legitimately
     extends to `20260529_0002`).
   - `test_standards_pack_build` errors (18): need `make standards-pack` first.
   - Integration tests needing external services/seeding not present in the
     testcontainer-only session: divalevale routing/full-chain, social ingestion
     (`DuplicateTableError`), validation-webhook delivery, circuit-breaker
     enforcement, one stub-auth test. These fail identically in isolation and
     exercise code the excision never touched.

## Build / dev server
7. The `npm run build` + `tsc --noEmit` gates were run in an isolated copy of
   `app/` (node_modules symlinked) so the running `next dev` on :3000 was not
   disturbed. The live `app/.next` was left untouched.
8. `/cockpit/aggregates` is auth-gated (the `(supervisor)` layout redirects to
   `/login` without a server-side session). A curl render check needs the full
   demo-login chain (Keycloak/API + persona seeding). The route's integrity is
   proven by the production build compiling the page and its entire KEEP import
   tree; a manual in-browser smoke check after `bash scripts/dev-up.sh` is
   recommended for final sign-off.
