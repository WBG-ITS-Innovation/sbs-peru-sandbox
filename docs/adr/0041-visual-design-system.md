# ADR 0041 — Visual design system

- **Status:** Accepted
- **Date:** 2026-05-22
- **Target prompt / Part:** Prompt 10 / Part 8
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

Prompt 10's supervisor UI ships five screens (cockpit, risk queue, findings, approvals, audit) plus a login flow and a demo persona switcher. WS3-WS7 will write screen-level code in their next slices. Without a design system landing first, those workstreams will each invent ad-hoc styling — different border radii, different severity palettes, different table row heights, different focus-ring colours — and the inconsistencies will surface on the May 25 projector when an SBS reviewer or the Superintendent scans across two screens in the same demo.

Five framing questions interact:

1. **Substrate.** Build the component library from scratch, pull an opinionated framework (Material UI, Mantine, Chakra), or use shadcn/ui's copy-the-source pattern. Each has different vendor-handoff and theming implications.

2. **Token shape.** Bind components to literal colour values, or to semantic CSS variables that a theme maps to literals. The two paths look the same until the native-speaker reviewer's review wants the high-band gold tweaked by 5° hue and the diff is either one line or forty.

3. **Severity tokens specifically.** The four severity bands (low / medium / high / critical) appear in many places: Badge, Toast, table row, anomaly card, KPI chip. How they're tokenised determines whether a hue / contrast review propagates cleanly or requires touching every consuming component.

4. **EmptyState as polish proof.** The places the demo audience sees an empty state are the places polish either holds up or collapses — the Conduct Unit Head opening Approvals when there are no pending items, the audit search returning nothing, a filter that doesn't match. A generic "No results" string is the regulator-UI failure mode. Custom empty states are the differentiator.

5. **Component index visibility.** Where reviewers (and future contributors) see "the design system" as a single artefact rather than as scattered components in a tree. The artefact's existence is its own credibility signal.

A sixth, smaller question is **information-density calibration**. The pressure-test note named "Bloomberg Terminal calibration, not Bloomberg Terminal cosplay" — dense and restrained, not austere or retro. This shows up in font features, numeric formatting, focus rings, and table styling.

## Decision

Six numbered decisions. Implementation lands in the same commit as this ADR (per the branch's decision-then-implementation pattern).

### D1 — shadcn/ui base + Radix primitives, copied source

The design system is built on [shadcn/ui](https://ui.shadcn.com/) — Radix UI primitives + Tailwind, copied into the repo at `app/src/components/ui/`. **The components live as repo source, not as a node-modules dependency.** This matches the regulator-handed-to-vendor constraint: a vendor inheriting the codebase reads the components and modifies them, no upstream package to track. Atlassian Design System, IBM Carbon, and Microsoft Fluent (the imported-package alternatives) were considered and ruled out on the same grounds.

The Radix primitives stay as imported npm packages (`@radix-ui/react-dialog`, `react-select`, `react-checkbox`, `react-toast`, `react-tooltip`, `react-slot`). They are stable, accessibility-audited, and the source we'd otherwise re-implement is itself unmaintained churn — the right place to draw the line is "Radix primitives in node_modules, shadcn wrappers in repo source."

### D2 — Severity (and every other status colour) bound to semantic CSS variables

Every severity-coded component reads from semantic CSS custom properties: `--severity-low-bg`, `--severity-low-fg`, `--severity-low-border`, the same four for `-medium`, `-high`, `-critical`. The tokens are defined once in `app/src/app/globals.css`; the theme maps them to the SBS palette literals (`#16a34a` for low through `#7c1d6f` for critical) per the canonical-light theme.

The same convention applies to status bands (`pending` / `in_review` / `resolved` / `escalated`), to surfaces (`--surface-elevated` etc.), and to focus / interaction states. **No component reads a hex literal directly.** A palette review touches `globals.css` only.

Failure mode this guards against: literal-hex bindings make a native-speaker-review tweak ("the high-band amber is too warm against the navy lockup") into a forty-component grep instead of a one-token edit.

### D3 — EmptyState as a real component, not a stub

The `EmptyState` component takes four required props and one optional:

- `icon: ReactNode` — a quiet illustration or icon (a Lucide stroke icon, sized 32px, not stock empty-folder clipart).
- `title: string` — one short sentence explaining what is empty and *why*.
- `body: string` — one sentence of context (what the user might be looking at, what they could do next).
- `primaryAction: { label: string, href: string }` — gets the user unstuck.
- `secondaryLink?: { label: string, href: string }` — optional, points at docs or a related view.

The four-piece shape (icon + title + body + primary + optional secondary) is the pattern across CFPB's complaint-search, GOV.UK Service Manual's empty-state guidance, and the GitHub web app. "No results" alone is the failure mode this guards against. Every async region in WS3-WS6 uses this component when its data set is empty — the lint rule for that lands with WS3.

### D4 — Component index page at `/app/_components`

A page exists at `/app/_components` that renders every component in every variant on one screen. Reviewers can audit the palette, typography, density, severity tokens, and inter-component visual agreement (Badge:critical sits next to Button:danger sits next to Severity:critical and they have to look like the same severity, or the inconsistency surfaces immediately).

The page is **not linked from the production nav rail.** It is reachable by URL only, which means QA can find it but a real end-user does not stumble into it. It renders in production builds (no `process.env.NODE_ENV` gating) because the URL is the canonical reference target for the ADR and downstream WS commit messages.

The page also enumerates which primitives are shipped versus reserved (Radio, Textarea, Popover, Toggle — see D6). Making the gap visible is what stops a future workstream from quietly reinventing one of the reserved primitives in their own screen module.

### D5 — Bloomberg Terminal calibration, not cosplay

Four specific calibration choices, each a 30-minute fix now versus a multi-hour retrofit later:

- **Inter font-features for small-size legibility.** The body element sets `font-feature-settings: "cv11", "ss01", "ss02", "ss03"`. The `cv11` ligature replaces the default single-storey `a` with the double-storey variant that reads better at 12px; the `ss0*` stylistic sets adjust the `1`, `l`, `i` shapes so they don't collide in narrow column widths.
- **Tabular numerals on every numeric column.** A `.tabular` utility class applies `font-variant-numeric: tabular-nums` and is used on every Badge confidence, KPI value, table number column, and the anomaly composite score. Without this, SSE-driven value updates make the row geometry jiggle as digits change.
- **Focus rings visible against navy backgrounds.** The default Tailwind / shadcn focus ring (`ring-2 ring-blue-500`) disappears against `#002244`. A custom `--focus-ring` token bound to `#F5BD24` (the SBS gold) provides a high-contrast outline against both navy headers and neutral table rows. The outline is `2px solid` with `2px offset` — visible without being noisy.
- **2px border radius, zebra on subtle.** Tables use `rounded-[2px]` (not `rounded-md` / `rounded-lg`). Zebra striping uses `neutral-50` on alternate rows, not a saturated tint. Thin 1px borders, not gridlines. These match the v2.1 spec's "deliberate, not retro" calibration.

### D6 — Primitives shipped versus reserved

**Shipped in this commit** (consumed by WS3-WS6 on day one):

| Component | Source | Notes |
| --- | --- | --- |
| `Button` | shadcn wrapper around Radix Slot | variants: default, secondary, ghost, destructive, link, outline |
| `Input` | native + tokens | one variant; focus + disabled states |
| `Select` | shadcn wrapper around `@radix-ui/react-select` | popover, scrollable list |
| `Checkbox` | shadcn wrapper around `@radix-ui/react-checkbox` | single + grouped |
| `Card` | native + tokens | with `Header` / `Body` / `Footer` slots |
| `Badge` | severity-coded, semantic tokens | variants: default, low/medium/high/critical + source / role chips |
| `Table` | native semantic HTML | tabular-nums, zebra, 2px radius, thin border |
| `Dialog` | shadcn wrapper around `@radix-ui/react-dialog` | the Modal primitive |
| `Sheet` | shadcn wrapper around `@radix-ui/react-dialog` (side variant) | the Drawer primitive |
| `Toast` | shadcn wrapper around `@radix-ui/react-toast` | severity-coded |
| `Tooltip` | shadcn wrapper around `@radix-ui/react-tooltip` | for the anomaly "why this fired" affordance specifically |
| `Skeleton` | tokens | for every async region |
| `EmptyState` | custom — D3 | the polish proof |
| `ErrorBoundary` | React class component + retry button | wraps every screen at the route boundary |

**Reserved** (deferred until a downstream workstream actually needs them):

- `Radio` — Findings filters use Select; no use case lands before WS6.
- `Textarea` — Approvals rationale uses a styled textarea inline until a multi-line input lands somewhere else.
- `Popover` — Tooltip covers the anomaly-card "why this fired" affordance.
- `Toggle` — the language switch uses Select; no toggle use case before WS3.

The component index page makes the reserved set visible so it does not become a "quiet reinvention" risk.

## Precedent

[market-comparators.md §5.A.V "Visual design system for regulator-grade interactive UIs"](../research/market-comparators.md#5av-visual-design-system-for-regulator-grade-interactive-uis-added-prompt-10-for-adr-0041) is the load-bearing reference. Three families cited there map to the decisions above:

- **Open government design systems** (GOV.UK Design System, USWDS, AU Government Design System, Canada.ca) — establish the "semantic tokens, not literal hex" pattern (feeds D2) and the "components named in terms of purpose" naming convention.
- **Information-dense financial UI references** (Bloomberg Terminal, Datadog, Grafana, AWS CloudWatch, CFPB Consumer Complaint Database, FCA Data Bulletin) — establish the calibration pattern (feeds D5: tabular-nums, subtle zebra, single accent for "look at this").
- **shadcn/ui as substrate** plus IBM Carbon / USWDS / Salesforce Lightning for severity tokens — feeds D1 (copy-the-source) and D2 (severity bound to semantic tokens).

## Divergence

- **Light-mode-only for May 25.** Bloomberg Terminal is dark-by-default; the SBS demo is light-by-default. The decision matches the v2.1 spec ("Light mode canonical for May 25") and the practical observation that supervisors will be running this on the same office monitors they use for everything else — a dark-mode-only UI surprises against the rest of their workflow. Dark mode is reserved as a Part 8 deliverable (semantic tokens already support it because they're CSS custom properties; the dark-theme map is what's deferred).
- **EmptyState breaks from shadcn's "no opinion on copy" stance.** Most design-system frameworks ship empty-state components that the consuming app must populate with text. SBS's EmptyState carries an i18n contract (the title / body strings must route through `t()`), and the demo's narrative consistency depends on the four-piece pattern being applied uniformly. The component enforces shape; the consuming code provides the keys.
- **Component index is canonically reachable, not gated.** Industry-standard "Storybook-as-internal-tool" practice is to gate the catalog in CI or behind a feature flag. This project's vendor-handoff constraint means the catalog should be reachable from a deployed instance — the URL is what the ADR cites. A future production overlay may move this to a non-production-only domain; for the May 25 deployment, it lives at `/app/_components` everywhere.

## Consequences

**Locks in.**

- Every severity-coded UI element reads from `--severity-<level>-{bg,fg,border}`. A future workstream wanting "but I need a slightly different red here" creates a *new* token, not a literal hex.
- The five empty states the demo audience will see (no anomalies, no pending approvals, no findings, no audit results, no queue items) all use the same component shape. A new screen that does not extend EmptyState fails reviewer-readability.
- The component index page is the canonical "show me the design system" answer. New components added by future workstreams must be added to the index.
- The Bloomberg Terminal calibration choices are not aesthetic preferences; they are accessibility and projector-legibility decisions. A workstream wanting to add a flashier interaction goes through an ADR amendment.

**Leaves open.**

- Dark mode. The token shape supports it; the dark-theme palette map is deferred.
- The four reserved primitives (Radio, Textarea, Popover, Toggle). Each lands when a downstream workstream needs it, alongside the component-index entry.
- Custom illustrations beyond Lucide icons. The empty states ship with icons in this commit; a hand-drawn illustration set is reserved for Part 8 (production-readiness).
- Storybook or a similar dedicated catalog framework. The component index is a single Next.js page; it scales for ~30 components. Beyond that, a dedicated Storybook is the right next step — not for May 25.

**Trail.** This ADR is the load-bearing reference for the design system implementation commit, the lint rule that enforces token-not-hex usage (lands with WS3 when the first real screen consumes the components), and every workstream that adds a component (the index page is the "did you forget to add yourself" check).
