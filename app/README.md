# SBS SupTech — supervisor UI

Next.js 14 (App Router) application served at `/app/`. Five screens:
cockpit, risk queue, findings, approvals, audit. Three demo personas:
the Conduct Supervisor, the Conduct Analyst, the Conduct Unit Head (CAD unit head).

## Layout

```
app/
├── package.json
├── tsconfig.json
├── next.config.mjs        # basePath: '/app'
├── postcss.config.mjs
├── tailwind.config.ts     # WS1 fills in the SBS palette
├── .eslintrc.json
└── src/
    ├── app/
    │   ├── layout.tsx
    │   ├── globals.css
    │   ├── page.tsx                  # /app/ → redirects to /app/cockpit
    │   ├── cockpit/page.tsx          # /app/cockpit
    │   ├── queue/page.tsx            # /app/queue
    │   ├── findings/page.tsx         # /app/findings
    │   ├── findings/[id]/page.tsx    # /app/findings/:id
    │   ├── approvals/page.tsx        # /app/approvals
    │   ├── approvals/[id]/page.tsx   # /app/approvals/:id
    │   ├── audit/page.tsx            # /app/audit
    │   ├── login/page.tsx            # /app/login
    │   ├── auth/callback/page.tsx    # /app/auth/callback
    │   └── _components/page.tsx      # /app/_components (design system index)
    └── i18n/                          # ES (canonical) + EN (toggle)
        ├── README.md
        ├── es.json
        └── en.json
```

## Local dev

```bash
cd app
npm install
npm run dev     # Next.js dev server on :3000, basePath /app
```

Open <http://localhost:3000/app/>.

## Production

The FastAPI process behind the institution-facing API reverse-proxies
`/app/*` to the running Next.js server (or to the static export, when
that lands). The `basePath: '/app'` in `next.config.mjs` matches that
URL shape so dev and prod render the same routes.

## Status by workstream

| Workstream | Owns |
| --- | --- |
| WS1 | `tailwind.config.ts`, `src/app/_components/page.tsx`, the design tokens consumed by every screen |
| WS2 | This scaffold, `src/i18n/`, OAuth + Keycloak, demo persona switcher |
| WS3 | `src/app/cockpit/page.tsx` + SSE wiring |
| WS4 | `src/app/findings/page.tsx` + `src/app/findings/[id]/page.tsx` |
| WS5 | `src/app/approvals/page.tsx` + `src/app/approvals/[id]/page.tsx` |
| WS6 | `src/app/queue/page.tsx`, `src/app/audit/page.tsx`, assignment endpoint |
| WS7 | SSE infrastructure on the FastAPI side; React hook lands here |

See `docs/PLAN.md` Part 8 for the broader frame.
