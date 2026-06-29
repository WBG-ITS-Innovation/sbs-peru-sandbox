# Part-17 hygiene — deferred decisions and flagged items

Nothing here was actioned. Each item needs a human decision (legal/naming/rights),
a coordinated change that exceeds mechanical-hygiene scope, or separate triage.

---

## A. Explicitly deferred by the prompt (no action taken — left as-is)

1. **Copyright holder in `LICENSE` / `NOTICE` / SPDX headers** — WBG OSPO decision.
   Left exactly as found. Do not guess the holder string.
2. **`annexo.pdf` redistribution rights** — rights decision. File left in place,
   unmodified. Confirm the source PDF may be redistributed under the chosen repo
   license before publishing.
3. **`CLAUDE.md` keep-or-strip for the public repo** — it is the internal working
   agreement (mentions internal subagents, `/close-prompt`, WBG tenancy). Decide
   whether it belongs in a public OSS repo.
4. **Spinner-state UX fix for non-escalated complaints** — frontend; needs human
   visual verification. (Workstream C documents that "triaged, not escalated" is
   correct behavior; the spinner that makes it *look* stalled is the separate UX
   item.)
5. **`CODEOWNERS` public-appropriateness** — confirm the owners listed are correct
   for a public repo.

---

## B. Migration items I chose NOT to remove (need human confirmation)

These are real orphans by the grep evidence, but removing them is a judgment call
beyond mechanical migration cleanup. Left untouched.

6. **`api/migrations/versions/20260528_0008_persona_tasks_and_actions.py`** +
   its dead model files
   `api/sbs_api/db/models/{manual_finding.py,digest_audit.py,incident_annotation.py}`.
   - All four tables (`persona_tasks`, `manual_findings`, `digest_audit`,
     `incident_annotations`) have **zero runtime references**: `persona_tasks` has
     no model at all; the other three have model files that **nothing imports**
     (classes `ManualFinding`/`DigestAudit`/`IncidentAnnotation` appear only in
     their own files). `manual_finding.py` imports `pattern_detection` but is itself
     unused.
   - Recommendation: remove the migration **and** the three dead model files
     together (a matched set from the excised RESHAPE persona-task surface), then
     relink `20260528_0009.down_revision` from `20260528_0008` → `20260528_0007`.
     Deferred because it couples migration + model deletion.

7. **Orphan tables inside the KEPT migration `20260528_0005`**:
   `sector_broadcasts`, `sector_broadcast_deliveries`, `sector_broadcast_audit`
   (+ their indexes). Unused (no model, no code refs), but the same migration also
   creates the still-used `social_signals`/`social_signals_fixture`/`fi_brand_aliases`.
   Stripping the orphan tables means surgically editing a kept migration. Deferred —
   decide whether to leave them (harmless empty tables on fresh DBs) or edit the
   migration.

---

## C. Pre-existing test failures (flagged for separate triage — NOT caused by part-17 hygiene)

The full `pytest` run is 748 passed / 6 skipped / **20 failed / 18 errors**. The
test schema is built via `Base.metadata.create_all` (not the alembic migrations),
so Workstream A cannot have caused these. Listed here so they are not lost.

8. **`tests/test_alembic_migration.py:146`** — stale head assertion:
   `assert version_num == "20260527_0001_agents_status"`, but the real (and
   pre-part-17) head is `20260529_0002`. Update the expected string to the current
   head. The migration chain itself applies cleanly.

9. **Other failures/errors** (logic/data/build-artifact, unrelated to migrations):
   `tests/agents/divalevale/*` (2), `tests/integration/test_divalevale_full_chain.py` (2),
   `tests/ingestion/social/*` (3), `tests/ops/test_circuit_breaker_enforcement.py` (1),
   `tests/auth/test_stub_auth.py` (1), `tests/webhooks/test_validation_delivery.py` (2),
   `tests/standards_pack/*` (8), and `tests/test_standards_pack_build.py` (18 errors,
   "build failed" — missing build artifact). Triage separately; several look like
   excision collateral or missing seed/build data, not regressions from this work.

---

## D. Tooling note

10. **gitleaks — no action needed.** The pinned **v8.21.2** gate was run and returns
    **0 findings** (`detect --source . --no-git --config .gitleaks.toml`). Noted only
    so future maintainers know: do **not** add `.secrets.baseline`,
    `docker-compose.yaml`, or `vendor/stoplight-elements/` to any new allowlist — the
    existing `.gitleaks.toml` already covers them; the 8 false positives seen in an
    early run were a v8.30.1 absolute-path artifact, not a config gap.
