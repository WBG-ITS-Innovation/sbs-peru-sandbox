# i18n contract — read this before adding a string

Spanish (`es-PE`) is canonical. English (`en-US`) is offered via a toggle.
Both dictionaries must have the same key set; CI fails on drift.

## Where strings live

```
app/src/i18n/
├── README.md       (this file)
├── es.json         (Spanish, canonical)
├── en.json         (English, parity-required)
├── index.ts        (the t() lookup function)
└── server.ts       (currentLocale() — reads the sbs-locale cookie)
```

Native-speaker review of `es.json` is non-negotiable. Luis Daniel
reviews the dictionary before May 25. No machine-translated string ships
without human review.

## Namespace taxonomy (pinned upfront)

The dictionaries are nested JSON; call sites use dotted paths. The
namespaces below are pinned so WS3/4/5/6 do not invent conflicting
conventions later. Adding a new top-level namespace requires updating
this README in the same PR.

| Namespace | Owns |
| --- | --- |
| `common` | Shared atoms used on every screen. `common.actions.*` carries verbs that appear in more than one place (approve, reject, edit, cancel, save, search, filter, sign-out). `common.severity.*` carries the four severity labels. `common.status.*` carries complaint resolution states. `common.locale.*` carries language-toggle labels. |
| `nav` | Left-rail nav labels and aria-labels. One entry per top-level route. |
| `auth` | Login flow, sign-in errors, session-expiry copy. |
| `cockpit` | WS3 — Tier 1 / Tier 2 panels, KPI strip, cross-source fusion strip, anomaly cards. |
| `findings` | WS4 — list, drilldown, BERT/XGBoost panels, agent reasoning, draft narrative. |
| `approvals` | WS5 — queue and detail, the four decision actions, rationale field. |
| `queue` | WS6 — risk queue table and filters. |
| `audit` | WS6 — audit log table, diff modal, search. |
| `errors` | RFC 9457 problem-type renderings and inline error messages. |

### Where action verbs go

**Shared.** Aprobar / Reject / Editar / Cancelar / Guardar all live under
`common.actions.*`. Putting them per-screen led to "Approve" being
translated three different ways in past projects.

A verb that is genuinely screen-specific (e.g., "Send to approvals" only
exists on Findings) stays on the owning namespace
(`findings.actions.send_to_approvals`), but the bar is "this verb is
meaningless outside this one screen." Default to shared.

## Adding a key

1. Add to `es.json` with the canonical Spanish string.
2. Add the same key to `en.json` with the English equivalent.
3. Call from the consuming component:
   ```tsx
   import { t } from '@/i18n';
   import { currentLocale } from '@/i18n/server';

   const locale = currentLocale();
   return <h1>{t(locale, 'cockpit.kpis.complaints_24h')}</h1>;
   ```
4. Run `npm run lint` to confirm the i18n gate stays green.
5. Run `pytest tests/integration/test_i18n_parity.py` to confirm the ES
   and EN key sets stay identical.

CI runs both gates. A PR that adds a key to one dictionary and not the
other will fail.

## Locale resolution

Server components call `currentLocale()` from `@/i18n/server`. It reads
the `sbs-locale` cookie and falls back to `es-PE`. The language toggle
in the top bar (WS2 OAuth commit) writes the cookie via a server action.

Client components receive `locale` as a prop from their server parent;
they call `t(locale, key)` directly. This keeps the client bundle free
of `next/headers`.

## Numbers, dates, currency

Always render through `Intl`:

```tsx
new Intl.NumberFormat(locale).format(1234.5);
new Intl.DateTimeFormat(locale, { timeZone: 'America/Lima' }).format(date);
new Intl.NumberFormat(locale, { style: 'currency', currency: 'PEN' }).format(245);
```

`America/Lima` is UTC−05:00 with no DST — confirmed for the May 25 demo.

## Why not next-intl / react-intl / lingui?

The contract here is intentionally small: a dictionary, a lookup, a
parity gate. Any of those libraries can replace `index.ts` without
changing call sites if we outgrow it. Until we hit pluralisation,
ICU MessageFormat, or RTL languages, the dependency is not justified.
