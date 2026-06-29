# Contributing

This is the project workflow. Read [CLAUDE.md](../CLAUDE.md) first — it defines the working agreement, the six north-star principles, and the closeout pipeline. This document is the practical walkthrough.

## One-time setup

```bash
# Install uv (Astral). See docs/setup/uv-quickstart.md for WBG-laptop notes.
# Once uv is on PATH, this single command creates .venv and installs all
# project + dev dependencies from pyproject.toml / uv.lock:
uv sync

# Install the pre-push hook (enforces branch naming)
bash scripts/setup_hooks.sh

# Install pre-commit hooks (gitleaks, detect-secrets, whitespace, .env guard)
uv run pre-commit install

# Generate a real detect-secrets baseline before first commit
# (the committed .secrets.baseline is a stub — see note below).
uv run detect-secrets scan > .secrets.baseline

# Copy the env template and fill in the four Azure OpenAI vars
# (WBG ITS tenancy — personal openai.com keys are not supported here)
cp .env.example .env
```

`uv sync` is the single install path. The application stack (FastAPI, Postgres, etc.) lands in Part 2 onward and is added to the relevant workspace member's `pyproject.toml`.

### Working with the Python project

The repo is a uv workspace. Members live under:

- `api/` — FastAPI service surface (scaffolded in Part 2).
- `agents/` — LangGraph agent layer (scaffolded in Part 6).
- `tools/` — MCP tool servers (scaffolded in Part 5).
- `sdk/` — generated client SDKs and shared client surface (scaffolded in Part 3).

The repo root holds shared dev dependencies (harness scripts, tests). Each workspace member has its own `pyproject.toml` for package-local dependencies.

The four commands you'll use day to day are `uv sync`, `uv run <cmd>`, `uv add <pkg>`, and `uv lock`. See [docs/setup/uv-quickstart.md](setup/uv-quickstart.md) for the short tour, including WBG-laptop installer notes and the Zscaler caveats. Locked decisions: [ADR 0021](adr/0021-package-manager-uv.md), [ADR 0022](adr/0022-python-version-3-12.md), [ADR 0023](adr/0023-workspace-layout-uv-members.md).

### Running the developer portal locally

The OpenAPI specification at [api/openapi/sbs-api-v1.yaml](../api/openapi/sbs-api-v1.yaml) is rendered as a navigable docs site via Stoplight Elements. To browse it locally:

```bash
bash scripts/serve-devportal.sh
# opens a server on http://localhost:8080/devportal/
```

The page loads Stoplight Elements from the unpkg CDN (vendoring is a Part 7 / Prompt 9 concern; see [ADR 0027](adr/0027-openapi-as-canonical-contract.md)). The OpenAPI document is the canonical contract; the Pydantic models in `api/sbs_api/models/` implement it. Whenever you change the models, regenerate the standalone JSON Schemas:

```bash
bash scripts/regenerate-schemas.sh
# writes api/openapi/schemas/<ModelName>.json
```

The integration test `tests/test_openapi_pydantic_match.py` asserts the OpenAPI specification and the exported Pydantic schemas agree on required fields, types, enums, formats, and patterns. Run it after any spec or model change:

```bash
uv run pytest tests/test_openapi_pydantic_match.py -v
```

To lint the OpenAPI specification with Spectral (project-local install — `npm install --no-save @stoplight/spectral-cli` if it is not already on disk):

```bash
./node_modules/.bin/spectral lint api/openapi/sbs-api-v1.yaml
```

### Running the API locally

The FastAPI service ships in Prompt 6 (Part 2 close). The local dev loop is three commands:

```bash
# 1. Bring up Postgres + Redis, apply Alembic migrations, seed demo
#    institutions + HMAC secrets, generate the dev CA + leaf certs,
#    seed oauth_clients with argon2-hashed credentials. Single command.
bash scripts/dev-up.sh
# Prints the DSN on success. Exits 2 if Docker is not reachable, 3/6 if
# postgres/redis did not become healthy, 4 if alembic migration failed,
# 7 if the dev CA / oauth-client seed step failed.

# 2. Run the API (binds 127.0.0.1:8000 by default; the auth-stub path).
bash scripts/run-api.sh

# 3. In a second terminal, exercise the running app end-to-end.
bash scripts/smoke-test.sh
# Asserts ETag round-trip, idempotency replay (match + mismatch),
# Location is fetchable, state machine forbidden transition, tenant
# binding, body size limit, canonical YAML reachable, traceparent
# header echo. Exits non-zero on the first failed assertion. Run with
# `SMOKE_RESET=1 bash scripts/smoke-test.sh` to wipe prior smoke
# artifacts before starting.
```

For the full signed-request path (mTLS + HMAC + OAuth + rate limit), use
the auth-chain variants:

```bash
SBS_API_MTLS_MODE=direct \
SBS_API_AUTH_STUB_ENABLED=false \
  bash scripts/run-api.sh

# In a second terminal:
bash scripts/smoke-test-auth.sh
# Exercises mTLS handshake → POST /v1/oauth/token → signed POST
# /v1/complaints → replay rejection → rate-limit 429 with four headers.
```

The API does not auto-serve `/openapi.json` or `/docs` — the canonical YAML is reached at `/v1/openapi.yaml` per [ADR 0028](adr/0028-fastapi-application-structure.md) §6. To browse the human-rendered docs, run `bash scripts/serve-devportal.sh` (separate process, no DB dependency).

Stop the stack with `bash scripts/dev-down.sh`. Add `-v` (`docker compose down -v`) to wipe both the Postgres and Redis volumes.

The `AUTH_STUB_ENABLED` setting is the foot-gun mitigation from [ADR 0028](adr/0028-fastapi-application-structure.md). `scripts/run-api.sh` defaults it to `true` so local dev "just works" without an mTLS client; the auth-chain path (see above) sets it to `false`, and protected endpoints then require mTLS + OAuth Bearer + HMAC signature per workstream F.7 (Prompt 7).

### First-time repo bootstrap (maintainer only)

After the repository is first created on GitHub, the maintainer runs this once to create the labels the workflow and CODEOWNERS rules depend on:

```bash
bash scripts/bootstrap_github_labels.sh
```

The script is idempotent — re-run it after any label set changes. New contributors do not need to run it.

### Working behind WBG networking

Contributors on WBG-issued laptops need a CA bundle configured so HTTPS-dependent commands work behind Zscaler. See [docs/setup/corporate-proxy-and-zscaler.md](setup/corporate-proxy-and-zscaler.md) — marked **DRAFT** until verified by a colleague on a clean machine. If you hit `CERTIFICATE_VERIFY_FAILED`, `UNABLE_TO_GET_ISSUER_CERT_LOCALLY`, or `tls: failed to verify certificate`, that document is the starting point.

### About the committed `.secrets.baseline`

The repository ships a stub `.secrets.baseline` because `detect-secrets` is not yet installed in the maintainer's environment and the baseline has to be generated against a real working tree to be meaningful. On your first clone:

```bash
pip install detect-secrets
detect-secrets scan > .secrets.baseline
git diff .secrets.baseline   # eyeball before committing
```

Re-commit the baseline only if it materially changes (e.g., a new file pattern was added or an old one removed). The baseline is a developer aid, not a CI gate — CI relies on gitleaks.

## Branch naming

The pre-push hook enforces this. Branches must match `main` or `part-NN/<slug>`.

Good:

- `main`
- `part-01/workflow-harness`
- `part-03/ingestion-tier-1`
- `part-07/developer-portal`

Bad (rejected at push time):

- `feature/anything`
- `othman/wip`
- `part-1/foo` (one-digit Part number — must be zero-padded)

Rename a branch with: `git branch -m part-NN/<slug>`.

## Starting a new prompt chat

Each prompt is executed in its own chat (Claude.ai or Claude Code instance). Cold-start chats can't see repo files; they need the current state of key project files pasted in as the first message. This avoids drift between summarized prior-chat memory and the actual state of `main`.

The workflow:

1. **Generate the context bundle.** From the repo root:

```bash
   bash scripts/prompt_chat_context.sh <part-number> | pbcopy
```

   On Linux, replace `pbcopy` with `xclip -selection clipboard`.

2. **Open a new chat** (Claude.ai or Claude Code). Paste the context bundle as the first message.

3. **Paste the prompt spec** as the next part of the same message (or as a follow-up message).

4. **Proceed.** The new chat now has real state to work against, not summarized memory.

The principle: **cold-start instances need real files, not prior-chat context.** Don't try to bypass this with "you already know the project" — that path leads to drift.

## Drafting the next prompt's spec

After a prompt merges, the next prompt's spec can be partially scaffolded:

```bash
bash scripts/next_prompt_scaffold.sh <next-prompt-number> <slug>
```

This generates a draft with:
- Mechanical scaffolding (predecessor commit, plan section, ADR numbering, standard checklists, standard closeout block) — auto-filled
- Strategic sections (scope adjustments, decisions to lock, ADRs to write, cross-review flags) — marked **TODO**

Edit the draft to fill in the TODOs. **Never paste a draft with TODOs into Claude Code.** The mechanical parts are automated; the strategic shaping is your judgment work.

Recommended workflow:
1. Generate the draft: `bash scripts/next_prompt_scaffold.sh 3 uv-project > /tmp/prompt-03-draft.md`
2. Open the draft in your editor
3. Fill in TODOs (typically 20-30 minutes of strategic shaping)
4. Optionally discuss the draft in your meta chat before pasting to Claude Code
5. Strip the "END DRAFT" line, then paste into the new prompt chat


## Commit messages

Conventional Commits. Type: one of `feat`, `fix`, `chore`, `docs`, `refactor`, `test`.

```
feat: add Tier 1 signed ingestion endpoint

POST /v1/complaints with mTLS + HMAC + Idempotency-Key.
Closes ADR 0003. Emits to Redis Streams.
```

`/close-prompt` generates a message from the staged diff. Edit it if the autogenerated one is too generic.

## The workflow

1. **Start a Part.** Run `/part-start <N>`. The session returns goals, prerequisites, open second-opinion items, and a ready-to-proceed question. Answer it before writing code.

2. **Decisions on the way.** Non-trivial decision: `/decision-log <text>`. Architectural decision: `/adr-new <slug>` and fill in the Precedent + Divergence sections.

3. **Subagents available throughout the session:**
   - `reviewer` — general code review.
   - `architect-guard` — refuses changes that contradict locked decisions without an ADR amendment.
   - `doc-sync` — catches code-doc drift.
   - `regulator-readability` — gates anything the Executive or the Superintendent will read.
   - `benchmark-checker` — verifies design changes cite a comparator.
   - `second-opinion` — adversarial reviewer, surfaces at least one weakness.

   Invoke them as the design takes shape, not only at the end.

4. **Close the prompt.** Run `/close-prompt`. The pipeline runs all six subagents on the staged diff, then a cross-model review, then an adversarial pass, then prompts for typed approval. There is no `-y` flag and no auto-merge. If anything blocks, fix and re-run.

   The cross-review step **hard-fails the closeout** if `scripts/cross_review.py` exits non-zero. If you genuinely cannot run it (VPN off, deliberate Azure-credential gap, scheduled outage), pass `--skip-cross-review-with-reason "<reason>"`. The reason is required, non-empty, and lands in the session journal under the cross-review section. Not appropriate uses: "the review came back ugly", "I don't have time". Backfill the review later via `python3 scripts/cross_review.py --target <whatever>`.

5. **PR review.** CI runs. Read the PR diff yourself. Merge manually via the GitHub UI when ready. Main is protected.

6. **Open the next prompt** with the paste-ready block from the session journal.

## When the pipeline blocks you

- `reviewer` blocks → fix the cited file:line.
- `architect-guard` blocks → either revert the locked-decision change, or open an ADR amendment in the same diff.
- `doc-sync` blocks → update the matched doc(s).
- `regulator-readability` blocks → rewrite using plain language; strike the banned phrasing.
- `benchmark-checker` blocks → add a `## Precedent` section citing a specific section of `docs/research/market-comparators.md`.
- `second-opinion` returns `WEAKNESS-FLAGGED` → decide: mitigate now, or log the weakness in the session journal under "deferred".

## What goes in `docs/reviews/`

Every `/cross-review` writes a file. The `## Triage` line is yours — disposition each finding as accept / defer / reject with a one-line reason. A review without a filled triage line is incomplete; `/close-prompt` flags it.

### Cross-review backend — Azure OpenAI (WBG ITS)

All cross-review calls go through Azure OpenAI in the WBG ITS tenancy. Personal `openai.com` keys are not supported and `scripts/cross_review.py` will fail validation on them. This is a WBG data-governance requirement (see ADR 0015).

Four env vars must be set in `.env` (or your shell) before `/cross-review` or the `/close-prompt` cross-review step can run:

| Variable | What it is | Where to get it |
| --- | --- | --- |
| `AZURE_OPENAI_API_KEY` | The WBG-issued key for the deployment | WBG ITS (or Azure portal: your resource → Keys and Endpoint) |
| `AZURE_OPENAI_ENDPOINT` | The resource endpoint, e.g. `https://<resource>.openai.azure.com/` | Azure portal: your resource → Keys and Endpoint |
| `AZURE_OPENAI_DEPLOYMENT` | The deployment **name** (not the model id) | Azure portal: your resource → Deployments |
| `AZURE_OPENAI_API_VERSION` | API version string, e.g. `2024-10-21` | WBG ITS or the Azure OpenAI release notes |

If any of the four is missing, the script fails with a clear message listing the missing variables. If you don't have WBG-issued credentials yet, run with `--skip-cross-review-with-reason "<reason>"` on `/close-prompt` — the rest of the pipeline still works, and you can backfill cross-reviews later.

## What never happens

- Auto-merge to main.
- Force-push to main.
- Skipping the typed approval gate.
- Editing an Accepted ADR in place — supersede it with a new one instead.
- Committing a real secret. `.gitignore` excludes `.env`, `*.pem`, `*.key`, `*.crt`. If you slip and commit one, rotate the secret first, then expunge from history.

## Getting help

- This file and [CLAUDE.md](../CLAUDE.md) cover workflow.
- [PLAN.md](PLAN.md) covers what to build and in what order.
- [DECISIONS.md](DECISIONS.md) covers what's been decided.
- The subagent definitions in [.claude/agents/](../.claude/agents/) explain each gate.
