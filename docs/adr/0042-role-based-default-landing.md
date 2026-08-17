# ADR 0042 — Role-based default landing

- **Status:** Accepted
- **Date:** 2026-05-22
- **Target prompt / Part:** Prompt 10 / Part 8
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

The supervisor UI has five screens (cockpit, risk queue, findings, approvals, audit) and three demo roles (supervisor, analyst, head). After a successful login, the user lands on *one* of those screens — the question is which, and based on what.

Three options:

1. **Same landing for everyone (the cockpit).** Simplest, but it makes the analyst and the head click past the cockpit on every login even though their work lives elsewhere.
2. **Last-visited screen.** The most personalised option, requires per-user state persisted server-side, and produces the "I closed my tab on the approval queue and re-opened it three days later" problem where the user lands on something they have forgotten the context for.
3. **Role-based default landing.** A static map from role to screen, evaluated once at the end of the OAuth callback. The decision is reviewable in code; the user reaches their primary workflow without an intermediate click.

The supervisor UI is workflow-driven — a head's day starts at Approvals, an analyst's day starts at Findings, a supervisor's day starts at the cockpit. Option 3 matches the workflow without requiring per-user state.

This ADR is small but worth pinning because workflow-driven landing decisions tend to acquire ad-hoc overrides ("just this one role lands on something different") that turn into a routing tangle. Capturing the rule in one place — in code, not in Keycloak — makes those overrides surface as a code change, not as a quiet IdP attribute edit.

## Decision

### D1 — Static role → landing route map, in code

The mapping lives in `app/src/auth/landing.ts`:

| Role (Keycloak realm-role name) | Landing route |
| --- | --- |
| `sbs:conduct:supervisor` | `/app/cockpit` |
| `sbs:conduct:analyst` | `/app/findings` |
| `sbs:conduct:head` | `/app/approvals` |
| (no matching role) | `/app/cockpit` (fallback) |

After the OAuth callback resolves the user's identity and writes the session, the callback handler reads the granted roles, looks up the landing route, and 302-redirects there.

### D2 — Multi-role precedence: most-specific first, then declaration order

A user with more than one matching role (rare in the demo, possible in production) is routed by the first match in the precedence list. The list lives in the same file as the map; "most specific" means "the screen the user spends the most workflow time on" — not a formal lattice. The demo has no multi-role users.

Production may grow this rule (segment-level overrides, maker/checker patterns); when it does, the same file gets the new map, and the change is a code review like any other.

### D3 — Persona switcher overrides the landing rule

In demo mode, the persona switcher changes the active persona without re-running the landing rule. Switching to Head from Supervisor's cockpit does not redirect to `/app/approvals`; the operator stays on the current screen with Head's identity. This matches the demo flow: the narrator wants to walk through cockpit → findings → approvals as one continuous experience, not three sign-in cycles or three landings.

Landing fires only on the OAuth callback (real login). The switcher's audit row (ADR 0040 D8) captures the from/to personas so the screen-level continuity is reconstructable in audit.

### D4 — The default-landing decision is captured in audit on first login only

The OAuth callback writes one `audit_events` row with `action='login'`, `meta={'role': …, 'landed_at': …}`. Subsequent in-session navigation does not write audit rows. WS6's audit screen sees one login row per session, not one per page view.

## Precedent

- [market-comparators.md §5.A.M.U "Supervisor-side user session auth"](../research/market-comparators.md#5amu-supervisor-side-user-session-auth-added-prompt-10-for-adr-0040) — the broader supervisor-edge auth precedent. Role-based default landing is the workflow-side companion to the auth chain pinned in ADR 0040.
- **Industry norm.** Salesforce, ServiceNow, ServiceNow's Now Platform, Atlassian Jira, GitLab and Microsoft 365 Admin Center all do role-based or persona-based default landing for workforce applications. The pattern is mature enough that it is unstated in the published security BCPs — it sits below the security layer, in the UX layer.
- **18F service design pattern: "start where the user's work starts".** 18F's design system patterns recommend landing the user at the screen most relevant to their role rather than at a generic home page that requires a second click. The pattern is the same one Salesforce implements for its Lightning Console personas.

## Divergence

- **No last-visited persistence in Prompt 10.** Industry-standard workforce apps frequently persist last-visited screen and offer "return where you left off" as a parallel affordance. This ADR commits to role-based landing only; last-visited is a Part 8 production add-on if user research surfaces a need.
- **Landing rule in code, not in Keycloak.** Keycloak supports a `client.home.url` attribute that could carry the landing route. Putting the rule in Keycloak couples UX routing to IdP configuration and makes the rule invisible to a reviewer reading the supervisor UI's code. Code is the right home — the same file holds the role-to-route map, the precedence list, and any future override; the IdP holds identity only.
- **Persona-switcher exception (D3).** A purist reading would re-run the landing rule on every persona switch. The demo flow needs continuity; the rule fires only on real login. This is an explicit demo affordance, not a security-relevant decision.

## Consequences

**Locks in.**

- One route per role. Changing a role's landing screen is a one-line change to `app/src/auth/landing.ts`, reviewable in the same PR as the screen change it accompanies.
- The audit row on login carries the landing decision. Superintendent can answer "where did each user land on May 25?" by reading the audit table; no separate telemetry needed.

**Leaves open.**

- Production multi-role precedence rules. Demo has no multi-role users; production will. The same file grows the rules when needed.
- Last-visited persistence. Not in Prompt 10; revisit if Part 8 user research surfaces the need.
- Per-user landing override (a "set my default screen" preference). Not in Prompt 10; revisit on user research.
