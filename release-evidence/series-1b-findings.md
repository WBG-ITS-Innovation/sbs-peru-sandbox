# Series 1b — Genericize Names, Complete .env.example, Rotation Hygiene

**Branch:** `chore/series-1-scrub` (continuing the Series 1 series; not a new branch).
**Repo:** `WBG-ITS-Innovation/sbs-peru-sandbox`.
**Operator:** unattended Claude Code session, 2026-06-01.
**Tools:** gitleaks `8.30.1`, trufflehog `3.95.3`, `git grep -P`, `openssl rand -hex 32`.

Series 1 removed regulator/contact/internal-infra identifiers and tightened
`.gitignore`. Series 1b takes three more local-hygiene passes on top:

1. **Persona genericization** — login personas (the names `maria` / `lucia` /
   `jorge`) become role-based (`supervisor` / `analyst` / `unit-head`) across
   every surface, including TypeScript persona-key types, Keycloak realm
   import, i18n labels and prose, and tests.
2. **Real-collaborator name sweep** — Fisnik, Antoine, Mariela, the Superintendent
   (Sergio), the SBS technical counterpart (Luis Daniel Allain Cañote), an SBS
   reviewer (Veronica), the FI integrator archetypes (Diego/Patricia/Roberto),
   and the demo narrator names are removed from the committable tree and
   replaced with role labels.
3. **Rotation hygiene** — the `SBS_API_INTERNAL_API_SECRET` (locally
   generated, not a portal credential) is regenerated and synchronised across
   `.env`, `app/.env.local`, root `.env.local`, and `.demo-internal-api-secret`.
   Three redundant secret-bearing backups (`.env.backup`, `.env.bak`,
   `app/.env.local.bak`) are deleted. The Azure OpenAI key cannot be rotated
   by Claude Code (portal-only) — the runbook for the human is at
   [`azure-key-rotation-runbook.md`](azure-key-rotation-runbook.md).

Plus: `.env.example` is now the full runtime contract.

All seven Series 1b gates pass. The Series 1 gates also still hold (re-checked
at Step 0). No runtime/agent logic was changed.

---

## 1. Persona genericization (Step 1)

### Mapping applied (canonical, deterministic)

| Was (name)  | Role               | New username/id | New email                          | New display name           |
|-------------|--------------------|-----------------|------------------------------------|----------------------------|
| `maria`     | Conduct Supervisor | `supervisor`    | `supervisor@sandbox.example.com`   | `Conduct Supervisor (Demo)`|
| `lucia`     | Conduct Analyst    | `analyst`       | `analyst@sandbox.example.com`      | `Conduct Analyst (Demo)`   |
| `jorge`     | Conduct Unit Head  | `unit-head`     | `unit-head@sandbox.example.com`    | `Conduct Unit Head (Demo)` |

Plus the contextual prose:
- "María Velásquez" (i18n example user) → "Conduct Supervisor (Demo)" / "Supervisor de Conducta (Demo)".
- "(María, Lucía, Jorge)" lists → "(Supervisor, Analyst, Unit Head)" / "(Supervisor, Analista, Jefe de Unidad)".
- "Jorge (head)" / "Lucía (analyst)" inline references → "the Unit Head" / "the Analyst".

### Surfaces changed (in lockstep — the Keycloak realm, the front-end demo definition, the test fixtures, and the docs MUST stay aligned or login flow 401s)

| Surface | Specifics |
|---|---|
| `app/src/auth/demo.ts` | `DEMO_PERSONAS` object keys, env-var names (`SBS_DEMO_SUPERVISOR_PASSWORD` etc., underscore for env-var compat with hyphenated key), password defaults (`supervisor-demo-2026` etc.), JSDoc. |
| `app/src/auth/session.ts` | `type Persona = 'supervisor' \| 'analyst' \| 'unit-head'` + operator-comment rewrite. |
| `app/src/components/shell/PersonaSwitcher.tsx` | `PERSONA_KEYS` array, label record shape, `labelFor` simplified to `labels[key]`. |
| `app/src/components/shell/TopBar.tsx` | `activePersonaKey` literal type, label record shape. |
| `app/src/app/(supervisor)/layout.tsx` | `inferActivePersonaKey` literal type + match arm, label record build (`'unit-head'` quoted key + `'personas.unit-head'` i18n path). |
| `app/src/app/api/auth/demo-login/route.ts` | `activePersonaKey: 'supervisor'`, `initial_persona: 'supervisor'`, `personas.supervisor.roles`. |
| `app/src/app/api/persona/switch/route.ts` | Body comment, audit-row example prose, error message (`'to must be one of: supervisor, analyst, unit-head'`). |
| `app/src/i18n/en.json` + `es.json` | `personas.{supervisor,analyst,unit-head}` label keys + values, `demo_section_body`, `demo_subline`, persona-hint body, `exchanges.user_label`. |
| `infra/keycloak/realm-sbs-demo.json` | Usernames, emails, `firstName`/`lastName` (now "Conduct Supervisor" / "(Demo)" so Keycloak's "firstName lastName" join renders the display name), password values, role-description prose. |
| `infra/keycloak/README.md` | Login-credentials table. |
| `api/sbs_api/audit.py`, `db/models/{audit_event.py,agent_feedback.py,pending_approval.py,supervisory_observation.py,complaint_narrative_draft.py}`, `findings/builder.py`, `routes/{findings.py,sse.py}` | Docstring examples and code comments. |
| `app/src/app/(supervisor)/approvals/page.tsx`, `app/src/app/_components/page.tsx`, `app/src/components/ui/Badge.tsx`, `app/README.md`, `app/src/i18n/README.md`, `app/src/app/api/auth/demo-login/route.ts` | Comments + UI labels. |
| `docs/adr/0040-supervisor-session-auth.md`, `docs/adr/0041-visual-design-system.md`, `docs/adr/0042-role-based-default-landing.md`, `docs/demo/2026-05-22-day1-close.md`, `docs/demo/2026-05-22-p10-true-close.md`, `docs/demo/2026-05-25-narration.md` | Prose: persona names → role labels; audit-row examples updated to new persona keys. |
| `tests/integration/{test_approvals_endpoints.py,test_audit_and_sse_completeness.py,test_findings_endpoints.py}`, `tests/test_{audit_event,internal_audit,persona_switch_audit_contract}.py` | Test fixtures: emails, persona-key strings (e.g. `"from_persona": "supervisor"`), and one interpolated synthetic `f"u{i}@sandbox.example.com"`. |
| `tests/integration/test_i18n_parity.py` | Comment about native-speaker review. |
| `scripts/{dev-seed.sql,seed_demo_narrative.py,close_prompt.py,next_prompt_scaffold.sh}` | Comments and seed content. |

### Hyphen-in-key note

The canonical persona key `unit-head` carries a hyphen so it reads as a kebab-case role label in URLs, Keycloak usernames, and audit-event meta. In TypeScript object literals that requires `'unit-head':` quoted-key syntax; the `labelFor` callsite is now `labels[key]` (bracket access) which is idiomatic for keyed dispatch. The env-var convention uses underscore (`SBS_DEMO_UNIT_HEAD_PASSWORD`) since env-var names can't carry hyphens.

### Verification

- All 35 persona-touched tests still pass (`tests/test_audit_event.py`, `tests/test_persona_switch_audit_contract.py`, `tests/integration/test_approvals_endpoints.py`, `tests/integration/test_audit_and_sse_completeness.py`, `tests/integration/test_findings_endpoints.py`).
- `scripts/demo.sh --scale small` PASS, exit 0, 3/3 batches, 3/3 listener.
- JSON files (`en.json`, `es.json`, `realm-sbs-demo.json`) all parse.

---

## 2. Real-collaborator name sweep (Step 2)

### Mapping applied

| Name(s) | Replaced with |
|---|---|
| `Fisnik` | `the WBG engagement manager` |
| `Antoine` | `the WBG technical lead` |
| `Yasemin`, `Palta` | `a WBG team member` |
| `Mariela` | `the SBS Conduct department head` |
| `Sergio` | `the Superintendent` |
| `Luis Daniel Allain Cañote` / `Luis Daniel` / `Allain` / `Cañote` / `Canote` / `Luis` (incl. possessive `Luis's`) | `the SBS technical counterpart` (or `the native-speaker reviewer`/`native-speaker-review` for ES-review references) |
| `Veronica` / `Verónica` | `an SBS reviewer` |
| `Diego` (compliance-officer archetype) | `a Tier-1 bank compliance officer (illustrative)` |
| `Patricia` (operations-manager archetype) | `a mid-size financiera operations manager (illustrative)` |
| `Roberto` (COOPAC-risk-officer archetype) | `a COOPAC risk officer (illustrative)` |
| `Oumaïma` / `Oumaima` (demo narrator) | `the narrator` / `another WBG operator` |
| `jtaquia`, `gcmif` | (already removed in Series 1 — confirmed re-zero) |

### Note on Othman

The prompt did not list `Othman` in the rename table. `Othman` appears in `CLAUDE.md` as the project maintainer and in several ADRs as a cross-review owner. Maintainer attribution is normal in a published repo; Series 1b leaves these untouched. Series 5 (publication-snapshot curation) may revisit if the publication audience is anonymised, but that is not in scope here.

### Files touched

41 files containing at least one collaborator name were edited. The substitutions were long-pattern-first (e.g. `Luis Daniel Allain Cañote` before `Luis`) so chained name patterns resolved cleanly.

Touched files include: `.claude/agents/{regulator-readability,second-opinion}.md`, `.github/{CODEOWNERS,ISSUE_TEMPLATE/feature.md,pull_request_template.md}`, `CLAUDE.md`, `docs/{CONTRIBUTING.md,DEMO.md,PLAN.md,DEFERRED.md,sprint-input-log.md}`, `docs/adr/{0014,0016,0019,0021,0025,0033,0036,0037,0038,0040,0041,0042,README}.md` (the ones containing names), `docs/explainers/prompt-01-workflow-harness.md`, `docs/prompts/prompt-08-tier-2-batch-and-synthetic-corpus.md`, `docs/research/market-comparators.md`, multiple `docs/sessions/*.md`, `docs/sessions/_template.md`, `docs/demo/2026-05-22-day1-close.md`, `docs/demo/2026-05-22-p10-true-close.md`, `docs/demo/2026-05-25-narration.md`, `app/src/{globals.css,tailwind.config.ts,i18n/README.md,app/(supervisor)/approvals/page.tsx,app/_components/page.tsx,components/ui/Badge.tsx,app/api/auth/demo-login/route.ts,auth/{demo,session}.ts,components/shell/{PersonaSwitcher,TopBar}.tsx,app/(supervisor)/layout.tsx,app/api/persona/switch/route.ts,i18n/{en,es}.json}`, `app/README.md`, `infra/keycloak/{README.md,realm-sbs-demo.json}`, `api/sbs_api/...`, `scripts/{close_prompt.py,next_prompt_scaffold.sh,dev-seed.sql,seed_demo_narrative.py}`, `tests/...`, plus `tests/integration/test_i18n_parity.py`.

### Verification (the NEW Gate 3)

```
Names swept: Fisnik|Antoine|Yasemin|Palta|Mariela|Sergio|Allain|Cañote|Canote|
             Veronica|Verónica|Diego|Patricia|Roberto|Oumaïma|Oumaima|Luis|
             maria|lucia|jorge|María|Lucía|Jorge|MARIA|LUCIA|JORGE

Hits in committable tree (excluding release-evidence/ where the names are
documented historically as the *targets* of the scrub):

  (zero hits — clean)
```

### Documented exceptions

The findings docs themselves (`release-evidence/series-1-findings.md` and this file) reference the historical names as the *targets* of the scrub. Those references are by design — without them the report would not be readable as evidence that the scrub took place.

---

## 3. `.env.example` completion (Step 3)

### Before

`.env.example` documented only `AZURE_OPENAI_*` (4 vars) + `GITHUB_REMOTE`. Contributors had no way to know what `SBS_API_*` knobs existed without reading `api/sbs_api/config.py` directly.

### After

`.env.example` now documents:

- **AZURE_OPENAI_*** (4 required) — harness LLM calls.
- **GITHUB_REMOTE** (1 optional) — harness git default.
- **SBS_API_*** (32 vars, all derived from `api/sbs_api/config.py` Settings fields, 1 required-when-supervisor-UI-deployed) — FastAPI runtime contract.
- **KEYCLOAK_*** (5 optional, defaults from `app/src/auth/config.ts`) — Keycloak base URL + realm + client id + redirect URIs.
- **SBS_INTERNAL_API_*** (1 required-when-supervisor-UI-deployed + 1 optional) — Next.js ↔ FastAPI bearer.
- **SBS_DEMO_*** (1 + 3 password overrides) — persona switcher toggle + per-persona ROPC password overrides.
- A footer noting that `LISTENER_OUTBOUND_SECRET_*` are intentional sandbox constants set by `docker-compose.yaml`/`dev-seed.sql` — NOT contributor-set.

Each line is marked `[REQUIRED]`/`[OPTIONAL]` and `[SECRET]` when applicable.

### Verification (Gate 4)

```
SBS_API_ fields in api/sbs_api/config.py:  32
missing from .env.example:                  0
```

Source of truth (`api/sbs_api/config.py`) was unchanged. `.env.example` is doc-only.

---

## 4. Rotation hygiene (Step 4)

### Pre-rotation on-disk inventory

| File | Held Azure key? | Held internal-API secret? | Disposition |
|---|---|---|---|
| `.env` | yes (`B99DHp…`) | yes (`7ba0bb04…`) | **kept** (canonical) |
| `.env.backup` | yes (same) | yes (same) | **deleted** |
| `.env.bak` | yes (same) | yes (same) | **deleted** |
| `.env.local` (root) | — | yes (same) | kept (single-line; see §6) |
| `app/.env.local` | — | yes (same) | **kept** (Next.js canonical) |
| `app/.env.local.bak` | — | yes (same) | **deleted** |
| `.demo-internal-api-secret` | — | yes (same) | **kept** (operator-convention single-line file) |

### Post-rotation on-disk inventory

| File | Holds Azure key? | Holds internal-API secret? |
|---|---|---|
| `.env` | yes (still `B99DHp…` — Azure rotation is portal-only, see runbook) | yes (`a9b964ca…` — new) |
| `.env.local` (root) | — | yes (`a9b964ca…` — synced) |
| `app/.env.local` | — | yes (`a9b964ca…` — synced) |
| `.demo-internal-api-secret` | — | yes (`a9b964ca…` — synced) |

- 3 redundant backups deleted → 4 → 1 file with the Azure key.
- New `SBS_API_INTERNAL_API_SECRET` generated via `openssl rand -hex 32`, synchronised across the 4 remaining files that hold it.
- `scripts/demo.sh --scale small` re-run with the new secret: PASS, exit 0, 3/3 batches, 3/3 listener.

### Azure key — runbook for the human

`release-evidence/azure-key-rotation-runbook.md` documents the four portal-side steps (regenerate KEY 1, paste into `.env`, smoke-test, audit usage log). Claude Code did NOT attempt the rotation — that requires WBG portal credentials it does not hold, and a forged rotation would mislead the operator.

If the rotation is deferred (portal access pending, change-window etc.), leave the existing `.env` value in place; the harness fails-closed on a bad key, which is louder feedback than a placeholder would produce. Document the deferral here and rotate at the next available window.

**Current status:** Azure key NOT yet rotated. Runbook present. Operator must execute Steps 1–4 of the runbook.

---

## 5. Verification gates (all seven pass)

| Gate | Result | Evidence |
|---|---|---|
| 1. `gitleaks detect --no-git` → 0 in committable scope | **PASS** | raw 13 hits, all in gitignored files; committable scope = 0. |
| 2. `trufflehog filesystem .` → 0 verified in committable scope | **PASS** | raw 91 hits, 0 verified, all in `.git/` / `.venv/` / `node_modules/` / `app/.next/` / `.scratch/` / `dev-ca/` / `dev-ca.zip` / `cloudflared`; committable scope = 0. |
| 3. Name-sweep gate (new): every collaborator + persona name → 0 hits | **PASS** | 26-name disjunction, zero hits in committable tree outside `release-evidence/`. |
| 4. `.env.example` documents every `SBS_API_*` field in `config.py` | **PASS** | 32/32 fields documented; 0 missing. |
| 5. Persona-touched tests pass with new role-based identities | **PASS** | 35/35 tests pass in 8.39s. |
| 6. `scripts/demo.sh --scale small` PASS, 3/3 batches, 3/3 listener | **PASS** | Exit 0; `webhook_pass_count: 3`, `batches_completed: 3`; summary written. |
| 7. Redundant on-disk secret copies deleted; old Azure key in ≤1 file | **PASS** | `.env.backup`, `.env.bak`, `app/.env.local.bak` deleted; Azure key now in `.env` only (was in 3 files). |

---

## 6. Residual notes / follow-ups

1. **Root `.env.local` is structurally redundant.** It carries only `SBS_API_INTERNAL_API_SECRET`, which `.env` already provides for the FastAPI service. The prompt's deletion list was explicit (`.env.backup`, `.env.bak`, `app/.env.local.bak`); root `.env.local` was not on it, so it remains on disk with the same fresh secret as `.env`. Operator can `rm .env.local` at any time without functional impact. Documented here for visibility.

2. **`docker-compose.yaml.bak` still on disk** (gitignored via `*.bak` from Series 1, so uncommittable). Not on the prompt's deletion list; left for operator cleanup. Contains the sandbox HMAC listener constants which are by-design allowlisted.

3. **Azure OpenAI key NOT yet rotated.** Portal-only action; runbook at `release-evidence/azure-key-rotation-runbook.md`. Operator must execute Steps 1–4 of that runbook. Until rotated, the previously-on-disk-in-three-places key is the live key; treat as exposed-at-rest and execute the rotation before any external publication.

4. **Test `test_audit_post_returns_404_when_secret_not_configured`** still fails environmentally because pydantic-settings reads `.env` even when `monkeypatch.delenv` clears the OS env — and `.env` now carries the new (non-empty) internal secret. Pre-existing issue documented in Series 1 §6; explicitly out of scope for Series 1b per the prompt. Will be fixed in Series 2 hygiene (the test fixture should `env_file=None` or use a tmp_path env-file override).

5. **Three-file persona-key fan-out.** `infra/keycloak/realm-sbs-demo.json` lists the demo users by `username` and `email`, both of which were updated. Contributors with an old Keycloak container holding the pre-rename realm must re-import; this was already flagged in Series 1 §6 and the rename in Series 1b extends it (the persona KEYS changed too, not just the email domain).

6. **Demo passwords changed.** The realm imports now seed passwords `supervisor-demo-2026`, `analyst-demo-2026`, `unit-head-demo-2026` (was `maria-demo-2026` etc.). Sandbox-only; documented in `infra/keycloak/README.md`'s login table.

---

## 7. Series 1 gates re-confirmed (baseline)

Done at Step 0. Series 1 added no new committable secrets; Series 1b inherits and extends. Re-running Series 1's grep sweep:

- `jtaquia` → 0 hits (outside findings)
- `compliance-ai-kg` → 0 hits (outside findings)
- `wbg-ca-bundle` → 0 hits (outside findings)
- `pa-wbg-decrypt` → 0 hits (outside findings)
- `*.worldbank.org` → 0 hits (outside findings)
- `*@sbs.gob.pe` (email form) → 0 hits (outside findings)

Series 1's `.gitignore` additions still hold; untracked-not-ignored set still empty.
