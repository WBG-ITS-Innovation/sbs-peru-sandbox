# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versioning is described in [CONTRIBUTING.md](CONTRIBUTING.md#versioning).
`main` is the release line.

---

## [Unreleased]

### Added

- `docs/PRODUCTION.md` — deployment guide for operators standing this up
  outside the SBS sandbox: reference topology, the two-API posture, mTLS
  termination modes, secret-vs-config inventory, Keycloak in production mode,
  managed Postgres/Redis with migration and backup guidance, observability,
  worker scaling, and an upgrade procedure with the ten gates as acceptance.
- `docs/OPERATOR-CHECKLIST.md` — the go-live gate list, in three owned
  sections (Deployment, Models, Governance). Linked from the top of the README.
- `CHANGELOG.md`, this file.
- Issue template for integration questions, and an issue-template chooser that
  routes vulnerability reports to private disclosure instead of a public issue.
- `scripts/perf-smoke.sh` — sandbox-scale indicative latency check. **Not a
  load test**; the checklist requires a real one.
- Supported-versions table and an explicit coordinated-disclosure window in
  `SECURITY.md`.
- Versioning statement in `CONTRIBUTING.md`.

### Changed

- **Next.js 14.2.35 → 15.5.23**, clearing all 21 Next.js security advisories
  (`npm audit` direct-advisory total 45 → 21; summary 9 → 7 findings). See the
  breaking-change note below.
- `docs/PRODUCTION.md` records that the cockpit's Redis session backend is
  **not implemented** — `SBS_SESSION_BACKEND=redis` exists only as a comment —
  so the cockpit is single-replica and a restart ends every session.

### Fixed

- **Polynomial-time ReDoS in the redaction engine** (CodeQL
  `py/polynomial-redos`, alerts #2 and #3). `_DNI_PATTERN` and `_RUC_PATTERN`
  separated the identifier keyword from its digits with `\s*[:.-]?\s*`; two
  adjacent unbounded `\s*` let N whitespace characters split N+1 ways, so a
  keyword followed by a long whitespace run cost O(N²). Redaction runs on
  attacker-influenced complaint narratives, making this a reachable
  denial-of-service surface. Both runs are now bounded. On 200,000 characters
  of adversarial input the engine went from roughly two minutes to 13.6 ms.

### Breaking

- **Next.js 15 App Router async request APIs.** `cookies()` now returns a
  Promise, and dynamic `params` are Promises. Anyone maintaining a fork of the
  cockpit must await both. Within this repository the migration is complete:
  the official codemod covered 45 files, its two `UnsafeUnwrappedCookies`
  escape hatches were undone by hand (`currentLocale()` and `activePersona()`
  are now async, with 29 call sites awaited and 10 server components made
  `async`), and `tailwind.config.ts` moved from `require()` to an ESM import
  because Next 15 loads that config through the ESM loader.

---

## [0.1.0-handover] — 2026-08-17

The open-source release train. This is the state handed over at the close of
the engagement: a production-ready reference implementation whose production
deployment requires completing `docs/OPERATOR-CHECKLIST.md`.

Released as the merge of `oss-release-pr` into `main`. No git tag was cut at
the time; this entry is the record.

### Added

- **Two-tier ingestion behind a real auth chain** — a near-real-time
  single-complaint API (`POST /v1/complaints`) and an authenticated batch
  channel (`POST /v1/batches`), both behind mutual TLS, OAuth2
  client-credentials with cert-bound tokens, and HMAC body signing, with
  per-institution rate limiting and idempotency. Both tiers land the same
  canonical record.
- **A supervised multi-agent pipeline** — validation (DIValeVale) → triage →
  conditional investigation → synthesis → cross-source correlation — running on
  both ingestion tiers, off the request path, over ten deterministic tools.
- **Azure OpenAI cloud provider**, and removal of the silent mock fallback:
  a misconfigured provider now fails at boot rather than fabricating analysis.
- **Per-run provider audit trail** — every `agent_runs` row records which
  provider actually served it, so a replayed fixture cannot be mistaken for
  live inference.
- **A supervisor cockpit** (Next.js, App Router) with a Keycloak-backed
  session, three demo personas, and a two-perimeter identity model.
- **A ten-stage verification gate suite** (`stage-a` … `stage-h-full`), where
  the `-full` gates run against the live compose stack with no mocks.
- `docs/ARCHITECTURE.md` — how the system actually works, cited to the code.
- `docs/HANDOVER-NOTES.md` — the sharp edges, the known-incomplete-by-design
  list, and errata against the audit trail.
- `DATA_PROVENANCE.md` — the synthetic-data pipeline as it actually exists.
- ORM models for the four tables that had none, plus a test guarding the
  inverse direction: no table-level autogenerate drift.
- A cleanup gate that fails if a real financial institution is ever named in
  committed data.

### Changed

- The README became a public front door, with the cockpit bootstrap documented
  including both API processes and the model provider.
- Anexo 1-A is documented as 27 fields — 23 base plus 4 conditional
  bancaseguros — and the UI tab renders all 27 under its "27 campos" heading.
- `run_agent_pipeline_on_new` is described as the backfill utility it now is.
- MIT license, with the WB-IGO rider.

### Fixed

- `next` bumped to 14.2.35, past CVE-2025-29927.
- The mock provider's script cursor is keyed per complaint.
- `.env` supplies defaults to `run-api.sh` rather than overriding them.
- The stage-h gate pair implemented; `stage-g-full` no longer skips its live
  half.
- Keycloak's compose healthcheck probes the realm it actually serves.
- `classify_complaint` keyed on the enums the API accepts.
- `rr1-2025.json` and `journey-emails.json` regenerated as fully synthetic —
  entities and prose both.

### Known limitations at this release

Carried forward deliberately; each is detailed in `docs/HANDOVER-NOTES.md`.

- The `on_prem` provider has never been observed against a real vLLM.
- DIValeVale records but does not gate, pending an institution-code mapping
  and an ADR 0026 decision on amount/currency.
- The cross-source correlator returns an empty result for every complaint
  except the golden one.
- `agent_runs.model_provider` is NULL for two reasons: rows predating migration
  `20260810_0001` (left un-backfilled rather than guessed), and runs on the
  journey / demo-ingestion path, which record NULL today. A
  `model_provider IS NOT NULL` filter drops both.
- `rank_features` returns a constant list; `reclamito`, `lupaman`, and
  `insight-chatbot` are registry entries with no runtime.

[Unreleased]: https://github.com/WBG-ITS-Innovation/sbs-peru-sandbox/compare/main...HEAD
