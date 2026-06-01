# Azure OpenAI key rotation — operator runbook

**Audience.** The maintainer (or whoever holds the WBG Azure portal credential for the SBS SupTech AOAI deployment).

**Why this exists.** The current `AZURE_OPENAI_API_KEY` was written to plaintext on disk in multiple files on the maintainer's laptop (`.env`, `.env.backup`, `.env.bak`). Series 1b consolidated those copies down to a single `.env`, but the key value itself has been exposed-at-rest for the duration the backups existed. Treat as compromised; rotate.

**What Claude Code did automatically (Series 1b).**
1. Generated a fresh `SBS_API_INTERNAL_API_SECRET` via `openssl rand -hex 32` and synchronised it across `.env`, `app/.env.local`, the redundant root `.env.local`, and `.demo-internal-api-secret`. The new value starts `a9b964ca…` on this run; it is sandbox-scoped (FastAPI ↔ Next.js bearer) and was not the portal-side key. The demo (`scripts/demo.sh --scale small`) was re-run with the new value end-to-end and PASSed.
2. Deleted three redundant secret-bearing backups: `.env.backup`, `.env.bak`, `app/.env.local.bak`.

**What Claude Code did NOT do** (and must NOT do silently). It did not rotate the Azure OpenAI key in the WBG Azure portal. That requires portal credentials Claude Code does not hold, and forging a rotation would be misleading. The steps below are for the human operator.

---

## Step 1 — Regenerate the AOAI key in the WBG Azure portal

1. Open https://portal.azure.com and switch to the WBG ITS tenancy.
2. Navigate to the Azure OpenAI resource that backs `AZURE_OPENAI_ENDPOINT` in your `.env` (the resource name was scrubbed from this repo in Series 1 — it is whatever your endpoint URL points at).
3. Open **Keys and Endpoint**.
4. The deployment has two keys (KEY 1 and KEY 2). Click **Regenerate** on the key currently in use. (If you don't know which one — both `.env` values map to "key 1" in the Azure portal convention; regenerate KEY 1.)
5. Copy the new key value to the clipboard.

## Step 2 — Paste the new key into the single canonical `.env`

```bash
# In the repo root on your laptop
cd /Users/omakhlouk/Projects/sbs-suptech-prototype  # or wherever your clone lives

# Open .env in your editor and replace the AZURE_OPENAI_API_KEY=... line.
# Do NOT echo the key on the shell history.
```

After saving, confirm the file is still gitignored:

```bash
git check-ignore -v .env       # expect: .gitignore:41:.env	.env
git ls-files .env              # expect: (empty — file is untracked)
```

## Step 3 — Confirm authentication

Run one of the cross-review smoke calls (any small call to the API will do):

```bash
PATH="$HOME/miniconda3/bin:$PATH" uv run python -c "
from openai import AzureOpenAI
import os
client = AzureOpenAI(
    api_key=os.environ['AZURE_OPENAI_API_KEY'],
    azure_endpoint=os.environ['AZURE_OPENAI_ENDPOINT'],
    api_version=os.environ['AZURE_OPENAI_API_VERSION'],
)
r = client.chat.completions.create(
    model=os.environ['AZURE_OPENAI_DEPLOYMENT'],
    messages=[{'role': 'user', 'content': 'reply with ok'}],
    max_tokens=10,
)
print('OK', r.choices[0].message.content)
"
```

Expected: `OK ok` (or similar) on stdout, exit 0. If the call returns 401, the new key was pasted wrong or the wrong KEY slot was regenerated.

## Step 4 — After the rotation lands

Once the new key authenticates:

1. Audit the Azure portal **Activity log** for any usage of the OLD key between the time it was first written to disk and the time of regeneration. If anything outside your laptop's outbound IP shows up, investigate.
2. If the project switches to using both KEY 1 and KEY 2 in a blue/green rotation pattern later, document the convention in `docs/setup/corporate-proxy-and-zscaler.md` so the next rotation does not repeat the on-disk fan-out that prompted this runbook.

---

## What if you can't rotate right now?

If the rotation has to wait (portal access pending, change-window restriction, etc.), leave `AZURE_OPENAI_API_KEY` in `.env` as the value it already has — but flag the deferral explicitly in `release-evidence/series-1b-findings.md` §4, and rotate as soon as the constraint clears. The Series 1b commit references this runbook by name; the deferral is visible to anyone reading the evidence trail.

Do **not** edit `.env` to a placeholder like `<ROTATE-ME>` unless you also pause cross-reviews — the harness will fail-closed when the value is non-empty-but-invalid, which is louder feedback than `<ROTATE-ME>` would produce.
