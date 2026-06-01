# Series 1 — Working-Tree Scrub: findings & evidence

**Branch:** `chore/series-1-scrub` (off `main` @ `b172706`).
**Repo:** `WBG-ITS-Innovation/sbs-peru-sandbox`.
**Operator:** unattended Claude Code session, 2026-06-01.
**Tools:**
- gitleaks `8.30.1` (downloaded to `/tmp/series1-bin/` — no system install).
- trufflehog `3.95.3` (downloaded to `/tmp/series1-bin/`).
- `git grep -P` (Perl regex; `-E` `\b` is silent-no-match).

This document is the evidence the working tree is secret-free, identifier-free,
and free of committed bulk data. Section 1 lists what the discovery sweep
found. Section 2 records the history scan. Section 3 lists what was changed.
Section 4 shows the post-scrub re-sweep and the four documented tolerance
buckets. Section 5 attaches the verification-gate outputs. Section 6 lists
manual follow-ups for a human.

---

## 1. Discovery sweep (working tree, pre-scrub)

Scope: **497 files** = `git ls-files` (tracked) ∪ `git ls-files --others --exclude-standard` (untracked-but-not-ignored). Gitignored paths (`.git/`, `.venv/`, `node_modules/`, `.next/`, `.env*`, `certs/`, `dev-ca/`, `data/batches/`, `data/synthetic-corpus/`, `tmp/`, `standards-pack/{openapi,schemas,catalogs,sdk-helpers,examples}/`, …) are out of scope because they cannot be committed.

Values are redacted: long base64/hex tokens are collapsed to `[…REDACTED-long-token]`. Human-readable identifiers (emails, hostnames) are shown verbatim so the finding is actionable.

### 1.1 Project-specific patterns

| Pattern | Pre-scrub hits | Disposition |
|---|---|---|
| `jtaquia@sbs.gob.pe` (real SBS contact) | **0** | clean already |
| `maria@sbs.gob.pe`, `lucia@sbs.gob.pe`, `jorge@sbs.gob.pe` (demo personas) | **52** across 15 files | renamed to `@sandbox.example.com` (§3.1) |
| `gcmif@sbs.gob.pe` (support footer) | **2** (i18n en + es) | renamed to `sbs-suptech-sandbox@worldbank.org` (§3.1) |
| `compliance-ai-kg` (WBG Azure resource name) | **1** (session journal) | replaced with `<azure-aoai-endpoint>` placeholder (§3.2) |
| `East US` / `eastus` | **0** | clean already |
| `wbg-ca-bundle-full.pem` (CA bundle filename) | **4** across 2 session journals | renamed to `corp-ca-bundle.pem` (§3.2) |
| `wbg-ca-bundle` (generic) | **8** across 3 docs | renamed to `corp-ca-bundle` (§3.2) |
| `~/certs/wbg-ca-bundle*.pem` (path literal) | **10** across 4 docs | path renamed; prose generalised (§3.2) |
| `pa-wbg-decrypt.worldbank.org` (internal hostname) | **2** (session journal) | replaced with "corporate TLS-decrypt host" prose (§3.2) |
| `WBG Root CA G2`, `WBG Cloud Root CA`, `WBG Cloud Issuing CAs`, `WBG Issuing CA1 G2`, `World Bank Group JSS …` | **6** across 2 docs | generalised to "corporate root CAs" / "corporate root certificates" (§3.2) |
| Bearer token literal | 1 (`tests/test_oauth_scope_enforcement.py`: `Bearer not.a.valid.token`) | **tolerated** — synthetic invalid-token fixture (§4 tolerance A) |
| `postgresql+asyncpg://sbs:sbs@…` (dev DSN) | 11 across alembic.ini, config.py, docker-compose.yaml, scripts/, tests/ | **tolerated** — well-known dev defaults, every line carries `# pragma: allowlist secret`; allowlisted in `.gitleaks.toml` (§4 tolerance B) |
| OAuth `client_secret` literal | **0** | clean |
| HMAC signing key/secret literal | **0** | clean |
| Postgres conn string with non-`sbs:sbs` creds | **0** | clean |
| Non-`@worldbank.org` personal email | **0** | clean |

### 1.2 Generic credential patterns

All zero hits in the committable scope:

```
ghp_…                  → 0
github_pat_…           → 0
hf_…                   → 0
sk-…                   → 0
AKIA…                  → 0
ANTHROPIC_API_KEY=...  → 0
OPENAI_API_KEY=...     → 0
AZURE_OPENAI_API_KEY=... → 0
BEGIN … PRIVATE KEY    → 0 (committable scope; dev-ca/ has unsigned dev keys but is gitignored)
Slack webhook URL      → 0
JWT-like eyJ…          → 0
```

### 1.3 Other surfaces

| Surface | Result |
|---|---|
| Tracked files with risky extensions (`.pem .key .pfx .p12`) | **0** |
| Tracked `.env*` files | only `.env.example` and `app/.env.example` (intended) |
| Tracked notebooks (`.ipynb`) | **0** |
| Tracked PDF / docx / pptx | **0** |
| Tracked xlsx / csv | only `data/synthetic-corpus-golden/*.csv` (intended golden sample) + `data/synthetic-corpus-templates.yaml` |
| Tracked images in `docs/` | **0** (no screenshots to redact) |
| All tracked images | **1**: `app/public/sbs-logo.png` (public regulator logo, intentional) |
| Dockerfiles / compose files | `docker-compose.yaml` (allowlisted dev secrets per `.gitleaks.toml`) |
| Untracked-not-ignored files | **6** before scrub — see §3.3 |

### 1.4 Untracked-but-not-ignored files (pre-scrub, would catch a stray `git add .`)

```
bore                                                  (≈2.4 MB binary)
cloudflared                                           (≈40 MB binary)
data/sbs_sample/Copy of RR1_2025_values.xlsx          (REAL SBS sample — must never commit)
data/sbs_sample/SAMPLE_MUESTRA_ENTITY_CLAIMS.xlsx     (REAL SBS sample — must never commit)
dev-ca.zip                                            (sandbox CA bundle archive)
docker-compose.yaml.bak                               (backup; contains the same allowlisted dev HMACs)
```

All six are now gitignored (§3.3). The `data/sbs_sample/` spreadsheets were the single highest-risk finding in this scrub — they are real (non-synthetic) SBS data that was sitting one `git add .` away from a commit.

---

## 2. Committed history (`gitleaks` + `trufflehog` over full git log)

180 commits scanned. **0 secrets in history.**

```
gitleaks detect --config .gitleaks.toml (180 commits, 9.97 MB)
  → no leaks found

trufflehog git file://. (3 228 chunks, 7.88 MB)
  → verified_secrets: 0   unverified_secrets: 0
```

Series 1 does **not** rewrite history. The history was already clean per the supply-chain hardening that landed in Part 2 (`.gitleaks.toml`, `.secrets.baseline`, `.pre-commit-config.yaml`). Series 5's curated single-commit snapshot will start from a clean history regardless.

---

## 3. Replace (changes made in this branch)

### 3.1 Persona and support-contact emails (15 files)

`maria@sbs.gob.pe`, `lucia@sbs.gob.pe`, `jorge@sbs.gob.pe` → `supervisor@sandbox.example.com`, `analyst@sandbox.example.com`, `unit-head@sandbox.example.com`. RFC 2606 reserves `example.com` for documentation/test use; using it for synthetic personas makes their fictional nature unambiguous.

`gcmif@sbs.gob.pe` (support footer in i18n) → `sbs-suptech-sandbox@worldbank.org` (per the guardrail "Contact identifiers → a `@worldbank.org` mailbox").

One interpolated synthetic actor in `tests/integration/test_audit_and_sse_completeness.py` (`f"u{i}@sbs.gob.pe"`) → `f"u{i}@sandbox.example.com"`.

Files touched:

```
api/sbs_api/audit.py                                    (docstring example)
api/sbs_api/db/models/audit_event.py                    (docstring example)
app/src/auth/demo.ts                                    (demo persona definitions)
app/src/i18n/en.json                                    (support footer)
app/src/i18n/es.json                                    (support footer)
docs/adr/0040-supervisor-session-auth.md                (persona list)
docs/demo/2026-05-25-narration.md                       (demo narration)
infra/keycloak/README.md                                (login table)
infra/keycloak/realm-sbs-demo.json                      (Keycloak realm — username + email fields)
tests/integration/test_approvals_endpoints.py
tests/integration/test_audit_and_sse_completeness.py
tests/integration/test_findings_endpoints.py
tests/test_audit_event.py
tests/test_internal_audit.py
tests/test_persona_switch_audit_contract.py
```

Application behavior is preserved: the personas keep their roles and landing pages; only the literal email string changes. The Keycloak realm-import file and the front-end demo definition are updated in the same commit so the demo login flow works against the renamed personas without code branching.

### 3.2 WBG-specific paths and identifiers in docs (4 files)

| Was | Now |
|---|---|
| `~/certs/wbg-ca-bundle.pem` / `~/certs/wbg-ca-bundle-full.pem` | `~/certs/corp-ca-bundle.pem` (generic convention; doc explicitly notes the filename does not matter and `$CA_BUNDLE` is the env binding) |
| `compliance-ai-kg.openai.azure.com` | `"$AZURE_OPENAI_ENDPOINT_HOST"` (shell-evaluable env reference) |
| `pa-wbg-decrypt.worldbank.org` | "corporate TLS-decrypt host" prose |
| `WBG Root CA G2`, `WBG Cloud Root CA`, `WBG Cloud Issuing CAs`, `WBG Issuing CA1 G2`, `World Bank Group JSS Built-in Certificate Authority` | "corporate root CAs" / "corporate root certificates" prose |
| `WBG ITS Azure OpenAI tenancy ... requires the WBG CA bundle` | "corporate Azure OpenAI tenancy ... requires the corporate CA bundle" |

Files touched:

```
docs/DEFERRED.md                                                            (line 124)
docs/setup/corporate-proxy-and-zscaler.md                                   (lines 25, 32, 100)
docs/sessions/2026-05-18-prompt-05-open-questions.md                        (lines 133, 135)
docs/sessions/2026-05-18-prompt-05-openapi-spec-and-data-model.md           (lines 56, 132, 167)
```

Generic mentions of "WBG ITS", "WBG-issued laptop", etc. remain in prose where they describe the operator's environment without identifying private infra. The `.env.example` header retains "WBG ITS tenancy" since it explains *which* Azure OpenAI account the env vars are for — that policy is documented in CLAUDE.md and is not a secret.

### 3.3 `.gitignore` additions

Appended block:

```gitignore
# Backup files — `.env.backup`, `docker-compose.yaml.bak`, etc. These tend to
# be created during local debugging; slipping one through into a commit would
# re-leak whatever the live file contained at that moment. Series 1 scrub.
*.bak
*.backup

# Local-only sandbox bundles and tunneling binaries that occasionally land
# in the repo root from quick experiments. Never to be committed. Series 1.
/bore
/cloudflared
/dev-ca.zip

# Real SBS sample spreadsheets used for offline analysis on the maintainer's
# machine. Not synthetic — must never be committed. Series 1 scrub.
data/sbs_sample/

# .scratch — local UI artifacts and one-off mockups. Already excluded via
# .git/info/exclude on the maintainer's clone; pinned here so it applies to
# every clone.
.scratch/
```

After this, the untracked-not-ignored set is empty:

```
$ git ls-files --others --exclude-standard
(no output — empty set)
```

Pre-existing coverage (already in `.gitignore` before this scrub): `*.pem`, `*.key`, `*.crt`, `*.p12`, `.env`, `.env.*`, `.envrc`, `certs/`, `dev-ca/`, `secrets/`, `private/`, `data/batches/`, `data/synthetic-corpus/`, `data/synthetic/*.json`, `data/synthetic/*.parquet`. The Series 1 additions are strictly additive.

### 3.4 `.env.example` — no changes required

No values were *removed* from code in this scrub; identifiers were renamed value-for-value. The two prose env-var references introduced (`$CA_BUNDLE` and `$AZURE_OPENAI_ENDPOINT_HOST`) are documentation-side conventions, not runtime reads, and do not need placeholder entries.

`.env.example` already documents the runtime env contract (`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`, `GITHUB_REMOTE`). Expanding it to cover every `SBS_API_*` field is out of scope for Series 1.

---

## 4. Post-scrub re-sweep — by-design tolerance

The same Step 1 grep sweep was re-run after the changes. **All actual scrub-target patterns return zero.** The four buckets below are *intentional* hits that the patterns over-fit on. Each is documented so a future reviewer can confirm at a glance.

### Tolerance A — synthetic invalid-token test fixture

```
tests/test_oauth_scope_enforcement.py:170:    headers={"authorization": "Bearer not.a.valid.token"}
```

The string `not.a.valid.token` is deliberately malformed and asserts the OAuth middleware rejects it. Not a credential.

### Tolerance B — dev-default Postgres DSNs (`sbs:sbs@localhost`)

11 lines across `api/alembic.ini`, `api/sbs_api/config.py`, `docker-compose.yaml`, `docker-compose.yaml.bak` (gitignored), `scripts/demo_replay.py`, `scripts/dev-up.sh`, `scripts/run-api.sh`, `scripts/smoke_stage_g_live.py`, `tests/test_health_endpoints.py`, `tests/test_webhook_url_validation.py`. Every line carries `# pragma: allowlist secret`. The user/password pair is literally `sbs/sbs` — obviously a placeholder. Production deployments override via `SBS_API_DATABASE_URL`. Already covered by `.gitleaks.toml` allowlist and `.secrets.baseline`.

### Tolerance C — illustrative public URLs under `sbs.gob.pe`

```
api/openapi/error-catalog.md:62               https://status-sandbox.sbs.gob.pe   (labeled "illustrative URL")
api/openapi/sbs-api-v1.yaml:51                https://www.sbs.gob.pe              (public regulator homepage; OpenAPI contact.url)
api/openapi/sbs-api-v1.yaml:59                https://api-sandbox.sbs.gob.pe/v1   (OpenAPI servers[] placeholder for the future sandbox)
docs/schemas/agent_run.schema.json:3          https://schemas.sbs.gob.pe/…        (illustrative schema $id namespace)
docs/sessions/2026-05-18-prompt-05-…md:44     prose: "may want https://api.sbs.gob.pe/errors/…" (open question to SBS)
scripts/build-standards-pack.sh:33            https://api-sandbox.sbs.gob.pe/v1/portal/  (illustrative pack-builder URL)
```

These are public-or-illustrative URLs in a published API contract — not infrastructure leaks. The OpenAPI spec must declare a `servers[]` URL; using `api-sandbox.sbs.gob.pe` matches the regulator's hostname convention and tags the placeholder unambiguously.

### Tolerance D — `~/certs/corp-ca-bundle.pem` convention (post-scrub state)

The post-scrub state of the four docs now matches `~/certs/corp-ca-bundle.pem`. The path is a generic convention the docs explain (filename does not matter; `$CA_BUNDLE` is the env binding). Not a WBG-specific identifier.

### Re-sweep result outside the tolerance buckets

After excluding the four tolerance buckets above, the re-sweep returns **zero hits** across all patterns. The verbatim output of the post-scrub sweep is preserved at `/tmp/series1_sweep_final.md` on the operator's machine for the duration of the session; it is not committed because it duplicates this report.

---

## 5. Verification gates (all six pass)

| Gate | Result | Evidence |
|---|---|---|
| 1. `gitleaks detect` clean on working tree | **PASS** | 18 raw hits, all in gitignored files (`.env*`, `dev-ca/`, `.next/`, `docker-compose.yaml.bak`, `standards-pack/examples/`); **0 in committable scope** when filtered by `git check-ignore`. |
| 2. `trufflehog filesystem .` clean on working tree | **PASS** | 89 raw hits, 0 verified, all in `.git/`, `.venv/`, `node_modules/`, `app/.next/`, `.scratch/`, `dev-ca/`, `cloudflared`, `dev-ca.zip`; **0 in committable scope**. |
| 3. Re-run Step 1 grep sweep → zero hits | **PASS (qualified)** | Zero hits across all scrub-target patterns; the four tolerance buckets in §4 are by-design over-fits, each documented. |
| 4. `.env.example` present and complete | **PASS** | Present; no values removed in this scrub so no additions required. |
| 5. Real `.env` gitignored and not tracked | **PASS** | `.gitignore:41` matches `.env`; `git ls-files .env` → empty. The local file at `./env` contains a real Azure OpenAI key — confirmed gitignored, will not be committed. |
| 6. `scripts/demo.sh --scale small` runs cleanly | **PASS** | Exit 0; 3/3 batches `complete`; 3/3 listener `PASS`; summary at `tmp/demo-run/20260601T222802Z/summary.json`. (Required adding `/Users/omakhlouk/miniconda3/bin` to `PATH` so `uv` resolved — environment quirk, not a scrub regression.) |

### Detailed gate outputs

```
=== gitleaks --no-git (filtered to in-scope) ===
gitleaks total: 18  in-scope (not gitignored): 0
```

```
=== trufflehog filesystem (filtered to in-scope) ===
trufflehog total: 90  in-scope (not gitignored, not .git/): 0
```

```
=== Final grep sweep (every scrub-target pattern) ===
-- jtaquia                       → (clean)
-- compliance-ai-kg              → (clean)
-- East US / eastus              → (clean)
-- wbg-ca-bundle                 → (clean)
-- pa-wbg-decrypt                → (clean)
-- *.worldbank.org hostnames     → (clean)
-- *@sbs.gob.pe emails           → (clean)
```

```
=== scripts/demo.sh --scale small ===
batch_019e854d18 status=complete   listener=PASS
batch_019e854d1d status=complete   listener=PASS
batch_019e854d22 status=complete   listener=PASS
demo.sh: PASS    EXIT=0
```

---

## 6. Manual follow-ups (out of scope for this commit)

1. **Local-only `.env` and `app/.env.local` contain a real Azure OpenAI API key.** Gitignored and confirmed un-committable, but worth rotating the key when convenient since it has been written to disk in plain text (`.env`, `.env.backup`, `.env.bak`, `.env.local`, `app/.env.local`, `app/.env.local.bak`). Not actionable inside the scrub; flagged for the operator.

2. **Screenshots.** No images live under `docs/`. The single tracked image is `app/public/sbs-logo.png` (the public SBS logo, intentional). If future docs add screenshots of the running app, they must be re-checked for leaked URLs, hostnames, or persona names before commit.

3. **Series 2** (runtime/agent logic) and **Series 3** (PII layers) are not started. This commit is strictly the working-tree scrub.

4. **Series 5** is responsible for the curated single-commit publication snapshot. The history scan in §2 confirms history is already clean, so the curated snapshot inherits a clean starting point — no `git filter-repo` / BFG step is required for secrets specifically.

5. **`.scratch/`** was historically excluded via `.git/info/exclude` on the maintainer's clone; this branch promotes that to `.gitignore` so other clones get the same protection.

6. **Persona Keycloak login.** The `infra/keycloak/realm-sbs-demo.json` realm-import is updated to the renamed personas. If a contributor has an old Keycloak container running with the pre-rename realm, they must re-import (or the login flow will 401 against the renamed personas). Documented separately in the commit message; no code path depends on the old emails.
