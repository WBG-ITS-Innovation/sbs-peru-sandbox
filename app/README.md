# SBS SupTech — supervisor UI

Next.js 14 (App Router) served under `basePath: '/app'`. Roughly twenty
page routes across three audiences — the supervisor cockpit, an
institution-facing (FI) surface, and integrator documentation — plus about
thirty BFF route handlers under `/app/api/*`.

Three demo personas: Supervisor (`supervisor`), Analyst (`analyst`), Head
(CAD unit head). Sessions are Keycloak-backed per ADR 0040; demo mode adds
a persona switcher and a one-click bootstrap.

**Running it takes more than `npm run dev`** — the cockpit fetches
server-to-server from a FastAPI process on `:8000`, and needs Keycloak for
its session. Full bootstrap is in the root [README](../README.md) under
"Run the supervisor cockpit". Operational caveats are in
[docs/HANDOVER-NOTES.md](../docs/HANDOVER-NOTES.md).

## Route groups

`src/app/(supervisor)/` is a **route group**: the parentheses are a
Next.js grouping convention and do *not* appear in the URL. A page at
`src/app/(supervisor)/cockpit/page.tsx` serves `/app/cockpit`. The group
exists so every supervisor screen shares one layout and one session
guard without nesting the URLs under a path segment.

The historically documented `/supervisor` path has never existed and 404s.

## Page routes

Supervisor surface — `src/app/(supervisor)/`:

| Route | Data |
|---|---|
| `/app/cockpit` | Live — server-rendered via `internalGet` |
| `/app/cockpit/aggregates` | Live — client fetches `/app/api/aggregates/*` |
| `/app/queue` | Live — client fetch |
| `/app/findings`, `/app/findings/[id]` | Live — server-rendered |
| `/app/approvals`, `/app/approvals/[id]` | Live — server-rendered |
| `/app/audit` | Live — server-rendered |
| `/app/analytics` | Live — client fetch |
| `/app/processing`, `/app/processing/[id]` | Live — client fetch |
| `/app/assistant` | Live — client fetch |
| `/app/admin` | Live — client fetch via `/app/api/admin/audit` |
| `/app/sandbox` | Live — client fetch, signed sends via `scripts/sandbox_send.py` |
| `/app/demo-journey` | Mixed — live fetches plus `@/lib/golden-complaint.json` |
| `/app/docs` | Static — Anexo 1-A / schema documentation |
| `/app/ingestion` | Static — renders `@/lib/journey-emails.json` |
| `/app/rr1` | Static — renders `@/lib/rr1-2025.json` |

Institution-facing surface — `src/app/fi/`:

| Route | Notes |
|---|---|
| `/app/fi/banco-demo-001/inbox` | Mixed — live fetches plus the golden complaint fixture |
| `/app/fi/banco-demo-001/send`, `/app/fi/coopac-demo-002/send` | Live — real signed sends |
| `/app/fi/banco-demo-001/submit/[rowIndex]` | Live |
| `/app/fi/banco-demo-001/triage/[rowIndex]` | Live |

Other:

| Route | Notes |
|---|---|
| `/app/` | Server-side redirect: no session → `/app/login`; otherwise the role-based landing route per ADR 0042 D1 (`/app/cockpit` for Supervisor) |
| `/app/login` | Keycloak authorization-code entry point |
| `/app/developers`, `/app/developers/credentials` | Static — integrator documentation |
| `/app/_components` | Design-system index |

Tables badged "datos de muestra / sample data" in the UI (social,
INDECOPI, SBS-DSC panels under `src/components/persona/`) are static
samples with no live endpoint, labelled as such deliberately.

## BFF route handlers

Everything the browser calls is a `/app/api/*` handler; the browser never
talks to FastAPI directly.

- `api/auth/*` — `login`, `callback`, `logout`, and `demo-login` (the
  demo-mode bootstrap; 404s unless `SBS_DEMO_MODE=true`)
- `api/persona/switch` — demo persona switcher
- `api/aggregates/*` — `trend`, `patterns`, `patterns-grouped`, `sources`,
  `social`, `feed`, `chat`; proxy to the backend
- `api/journey/*` — `stats`, `recent`, `insights`, `findings`, `audit`,
  `submit`; these shell out to `scripts/` and query Postgres directly
  rather than going through the backend, so they show no backend call
- `api/sandbox/*` — Tier-1 and Tier-2 send/status, via real signed senders
- `api/complaints/[id]`, `api/findings/[id]/*`, `api/approvals/[id]/[action]`,
  `api/admin/audit`, `api/explain/[key]`, `api/ingest`, `api/demo/assistant`
- `api/sse/[topic]` — server-sent events

Routes that spawn a Python script resolve the interpreter through
`src/lib/python.ts` (`SBS_PYTHON_BIN`, defaulting to `<repo>/.venv/bin/python`).

## Layout

```
app/
├── next.config.mjs        # basePath: '/app'
├── tailwind.config.ts     # SBS palette
└── src/
    ├── app/
    │   ├── (supervisor)/   # route group — not a URL segment
    │   ├── fi/             # institution-facing surface
    │   ├── api/            # BFF route handlers
    │   ├── developers/
    │   ├── login/
    │   └── _components/
    ├── auth/               # session, cookies, personas, Keycloak
    ├── components/
    ├── lib/                # api.ts, python.ts, sandbox-runner.ts, fixtures
    └── i18n/               # ES (canonical) + EN (toggle)
```

## Local dev

```bash
cd app
npm install
npm run dev     # :3000, basePath /app
```

Open <http://localhost:3000/app/api/auth/demo-login> for a demo session,
which lands on `/app/cockpit`. Note the redirect targets `0.0.0.0:3000`;
browsers follow it fine, scripted clients should request `/app/cockpit`
directly with the returned `sbs-session` cookie.

`npm run build` writes to `app/.next`, the same directory `npm run dev`
serves from, so building while a dev server is running breaks it. Stop
the dev server first, or expect to `rm -rf .next` and restart.

## Production

The FastAPI process reverse-proxies `/app/*` to the running Next.js
server. `basePath: '/app'` matches that URL shape, so dev and prod render
the same routes. See [docs/DEPLOY.md](../docs/DEPLOY.md).
