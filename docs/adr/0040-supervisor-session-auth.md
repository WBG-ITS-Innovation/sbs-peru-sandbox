# ADR 0040 — Supervisor session auth

- **Status:** Accepted
- **Date:** 2026-05-22
- **Target prompt / Part:** Prompt 10 / Part 8
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

Prompt 10 lands the supervisor UI at `/app/`. The institutional-edge API at `/v1/*` already has its auth chain (ADR 0031 mTLS + ADR 0032 OAuth 2.0 client_credentials with cert-bound JWTs + ADR 0033 rate limiting + the ADR 0027 amendment HMAC contract). That chain authenticates *institutions* on the wire and does not involve interactive users.

The supervisor UI is a different perimeter: interactive sessions from SBS staff (María, Lucía, Jorge) sitting inside the regulator's network, talking to the same backend over HTTPS. Reusing the institutional auth chain at this perimeter is the wrong fit — mTLS would require every supervisor's browser to present a cert, HMAC signing would need a per-supervisor secret, and the cert-bound OAuth tokens are sized for service-to-service traffic, not for interactive sessions with their own expiry and refresh semantics. The two perimeters need two auth chains; this ADR locks the supervisor-edge chain.

Six framing questions interact:

1. **Perimeter split.** Does the supervisor UI live inside or outside the institutional edge? Where exactly is the boundary, and which auth primitives stay with each side?

2. **Interactive flow.** Authorization Code with PKCE is the standards-level recommendation (RFC 9700). Are there reasons SBS should depart, or do we adopt it without modification?

3. **Token storage.** Where do the OAuth access and refresh tokens live? Browser storage (cookies, localStorage, sessionStorage, indexedDB) versus a server-side session map keyed by an opaque cookie.

4. **CSRF protection.** With a session cookie carrying state-mutating authority, what synchroniser-token pattern protects non-GET requests?

5. **SSE refresh contract.** Server-Sent Events streams use the same bearer token as the rest of the API. When that token expires mid-stream, the client must refresh and reconnect without losing topic subscription state or events. WS7 implements SSE; this ADR pins the contract so the implementation and the session model do not drift.

6. **Sandbox IdP versus production SSO.** The demo runs against a Keycloak sandbox; production runs against whatever SSO SBS already operates. How is the sandbox seeded reproducibly, and what changes in the production overlay?

A seventh, demo-only question is the persona switcher (ADR 0042 land alongside this one; the switcher implementation is feature-flagged behind `SBS_DEMO_MODE`). The switcher's compromise on token-acquisition shape — Resource Owner Password grant for all three demo personas at sign-in — is permitted only because the demo realm has known, sandbox-only passwords; production never enables it.

## Decision

The supervisor perimeter is a separate auth chain, locked as follows.

### D1 — Perimeter split

Two perimeters exist; the institutional edge is unchanged.

- **Institutional edge (`/v1/*`)** — unchanged from ADRs 0031, 0032, 0033, 0027-amendment. mTLS + OAuth client_credentials with cert-bound JWTs + HMAC body signing + per-institution rate limiting. No interactive sessions. No browser clients.
- **Supervisor edge (`/app/*` + supervisor-only `/api/*` route handlers + supervisor-only `/v1/internal/*` FastAPI routes)** — OAuth 2.0 Authorization Code with PKCE for the login flow, opaque-cookie server-side session for the rest. No mTLS, no HMAC at this perimeter; the network boundary is the agency LAN plus TLS.

Any future cross-perimeter access (a supervisor calling a `/v1/*` route on behalf of an institution) goes through an explicit on-behalf-of token exchange (RFC 8693), not by reusing one perimeter's auth at the other.

### D2 — Authorization Code with PKCE for production

The interactive login flow is Authorization Code with PKCE (RFC 7636), per the OAuth 2.0 Security BCP (RFC 9700 §2.1.1). The Keycloak client is `publicClient: true` with PKCE method `S256`, exactly as the BCP and the OWASP ASVS 5.0 §V3 prescribe. The Implicit grant is not used. The Resource Owner Password Credentials grant is not used except in the demo-mode persona switcher (D7).

### D3 — Opaque-cookie session; tokens never reach the browser

The browser only ever holds **one** cookie that carries any authority: `sbs-session`, an HttpOnly + Secure + SameSite=Lax + Path=/ + opaque random identifier (32 bytes, base64url). That cookie is the only key into the server-side session store.

The session store holds, per session id:

- The active OAuth access token (JWT issued by the IdP).
- The matching refresh token.
- The user identity (`sub`, email, granted scopes).
- The active persona pointer (demo mode only — see D7).
- Token expiry timestamp and last activity timestamp.

The session store is an in-process Map in Prompt 10. Production migrates it to Redis under `SBS_SESSION_BACKEND=redis` (Helm-values change, no code-shape change). The Redis path is the same `session_id → {…}` map with TTL handled by Redis itself.

Tokens **never** appear in any browser-readable storage. Not localStorage, not sessionStorage, not indexedDB, and not other cookies. A CSRF or XSS that exposes the session cookie costs the single active session; with the previously-considered alternative (one cookie per persona token) the same attack would cost every persona the operator could switch into.

### D4 — CSRF double-submit on non-GET

Every state-mutating request (`POST`, `PUT`, `PATCH`, `DELETE`) carries:

- The session cookie (sent automatically by the browser).
- An `X-SBS-CSRF` header whose value matches a second cookie `sbs-csrf` (issued at session start, regenerated on rotation, not HttpOnly so the JS client can read it).

The server-side session middleware rejects any state-changing request whose header does not match the cookie. The pattern is the OWASP Synchroniser Token (double-submit cookie variant) and is what 18F's `cg-deck` and Keycloak's admin console implement. SameSite=Lax on the session cookie is belt-and-braces; the double-submit check is the load-bearing defence.

GET requests do not require the CSRF header. SSE streams open via GET and inherit the session cookie; their refresh model is D5.

### D5 — SSE refresh contract (pinned now, implemented WS7)

When an SSE stream's session expires mid-stream:

- The server terminates the stream and emits a final SSE event `{event: "session-expired"}` carrying a transient correlation id.
- The client (the React `useSSE(topic)` hook from WS7) catches the disconnect, issues a `POST /api/auth/refresh` (silent refresh — uses the refresh token held in the server-side session, no user interaction), and on success reconnects to the same SSE endpoint with the `Last-Event-ID` HTTP header set to the last event id the client successfully processed.
- The server resumes the same topic subscription from the new session id; the topic + scope check is re-evaluated against the refreshed token (so a scope change on refresh is honoured, not ignored).
- The server replays events from `Last-Event-ID` forward using the Redis-backed stream backing the topic (WS7 lands the Redis stream; this ADR pins that it must be id-resumable).
- If the refresh itself fails (refresh token expired, refresh-token reuse detected, IdP unreachable), the client redirects to `/app/login`.

This contract is the WS2/WS7 integration gate. WS2 lands the refresh endpoint and the session model that supports id-resumable subscriptions; WS7 lands the SSE wire format and the Redis-backed stream. The contract pinned here is what stops them from drifting into incompatibility.

### D6 — Keycloak realm export (not init script)

The sandbox IdP is Keycloak, pinned at `quay.io/keycloak/keycloak:25.0.6` (no floating tag, no `latest`). The realm is seeded from a committed JSON file at `infra/keycloak/realm-sbs-demo.json` via the `--import-realm` flag (Keycloak 22+) at container startup.

Init-scripts that hit the Keycloak admin API on container readiness — the alternative considered — race the readiness check on cold-start: the admin endpoint becomes available before the realm provisioning hooks finish, so the script's first POST can land while the realm is half-loaded, producing intermittent failures that only manifest on certain hardware speeds and only on first boot. The export-and-import pattern reads from disk at the same lifecycle phase as the rest of Keycloak's realm loading; there is no race.

The realm is re-exportable: a developer who edits the realm in the Keycloak admin UI runs `bash infra/keycloak/export-realm.sh` to regenerate the JSON. The exported JSON is committed; the in-memory state of a running Keycloak container is not the source of truth.

### D7 — Three demo role scopes; production role model deferred

The realm seeds three users + three realm-roles:

- `maria@sandbox.example.com` — role `sbs:conduct:supervisor`. Lands on `/app/cockpit`.
- `lucia@sandbox.example.com` — role `sbs:conduct:analyst`. Lands on `/app/findings`.
- `jorge@sandbox.example.com` — role `sbs:conduct:head`. Lands on `/app/approvals`.

Role-based default landing is the subject of ADR 0042 and is the only consumer of the role claim in Prompt 10. The role-to-route mapping is in code (`@/auth/landing.ts`), not in Keycloak.

These three roles are a **demo scaffold**. The production role model maps to SBS's actual org chart (segment-level scoping for large banks vs financieras vs COOPACs, maker/checker on high-severity findings, multi-level approval chains for committee decisions). That model lands with Part 8 production work; this ADR does not commit to its shape beyond "the auth chain supports it without redesign — the same Keycloak realm, additional roles, the same client."

### D8 — Demo-mode persona switcher (feature-flagged)

The demo-mode persona switcher (ADR 0042 covers its routing implications; the implementation lands in this same prompt) acquires tokens for all three demo personas at sign-in via the Resource Owner Password Credentials grant (RFC 6749 §4.3) and stores all three in the session. The switcher updates an active-persona pointer in the server-side session; the active token returned by the session middleware changes accordingly.

This is gated behind `SBS_DEMO_MODE=true`. In production, the flag is off, the `directAccessGrantsEnabled` setting on the Keycloak client is off, and the ROPC path is not reachable. The deprecation framing of ROPC (RFC 9700 §2.4) applies to new external integrations; first-party use against a sandbox realm with known passwords for a demo-only feature flag is the explicit exception RFC 9700 carves out.

Every persona switch lands one row in `audit_events` (ADR 0040 alone does not own `audit_events`; that's the WS2 audit-substrate commit). The row carries `action='switch-persona'`, `actor_id=<operator email>`, `meta={'from_persona': …, 'to_persona': …}`. The `from`/`to` shape is the contract that makes the audit row useful — without it, the row only says "the operator switched persona at 14:32", which is not an audit trail.

## Precedent

- [market-comparators.md §5.A.M.U "Supervisor-side user session auth"](../research/market-comparators.md#5amu-supervisor-side-user-session-auth-added-prompt-10-for-adr-0040) — the load-bearing reference. Four pillars cited there:
  - **Authorization Code with PKCE** per RFC 9700 §2.1.1 (the OAuth 2.0 Security BCP, current as of January 2025). Adopted in D2.
  - **Opaque session cookie + server-side store**, tokens never in browser storage, per OWASP Session Management Cheat Sheet, OAuth BCP §6.2, and 18F's `cg-deck` reference implementation. Adopted in D3.
  - **Keycloak realm export** with `--import-realm` on Keycloak 22+, mirroring HMRC Making Tax Digital and OBIE Directory's sandbox-IdP pattern. Adopted in D6.
  - **SSE auth refresh** preserving topic + `Last-Event-ID`, per the WHATWG EventSource specification. Pinned in D5.

## Divergence

- **Demo-mode ROPC.** RFC 9700 §2.4 deprecates the Resource Owner Password grant for new applications. D8 enables it for the demo-mode persona switcher only — first-party trusted client, sandbox realm with known passwords, feature-flagged off in production. This is the carve-out RFC 9700 §2.4 leaves open ("the grant type … MAY be supported when … no other flow is technically feasible"), applied to the narrow case of a single-operator interactive demo against a sandbox realm. Production removes the carve-out by setting `SBS_DEMO_MODE=false` and `directAccessGrantsEnabled: false` on the Keycloak client.
- **In-process session store in Prompt 10; Redis in production.** OWASP and the OAuth BCP do not prescribe a specific storage backend, only that tokens stay server-side. The in-process Map is fine for the demo and for any deployment with a single supervisor-UI process; Redis is required for multi-replica deployments and is the Part 9 deliverable. The store interface is the same across both; the swap is a Helm-values change.
- **Role-based default landing in code, not in Keycloak.** Keycloak supports role-based home-URL hints, but tying landing to a Keycloak attribute couples the UI's routing to the IdP's configuration shape. Landing rules live in `@/auth/landing.ts` so the routing decision is reviewable in the same PR as the screen it lands on.

## Consequences

**Locks in.**

- The browser never holds an OAuth token directly. A future "let the React client talk to Keycloak in the front channel" pattern would be a perimeter break and is therefore an explicit re-litigation event, not an incremental change.
- CSRF double-submit on every state-changing request. WS3/4/5/6 all-mutation routes must read `X-SBS-CSRF` from the request and route through the same middleware.
- The SSE refresh contract is the integration gate between WS2 and WS7. WS7 cannot define a non-id-resumable topic without breaking the contract pinned here; the test for the contract lands with WS7.
- Production SSO integration is a configuration change (Keycloak federation), not a code change. The Helm overlay that points at the agency's IdP replaces the sandbox realm with the federation config; the client-side code does not move.

**Leaves open.**

- The production role model. Three demo roles are not the production model; that lands with Part 8 production work and gets its own ADR. The current code structure supports an arbitrary role set against the same Keycloak realm.
- The audit-event consumers (WS5 approvals, WS6 audit screen) own their action-vocabulary additions; this ADR commits only to `login`, `logout`, `switch-persona` for WS2.
- The on-behalf-of token exchange (RFC 8693) for cross-perimeter access has no current consumer. When a supervisor needs to call an institutional `/v1/*` endpoint on behalf of an institution — likely Part 8 production work — the exchange pattern is the right shape; the ADR for it lands at that time.
- Session-fixation defense (regenerating session id on privilege escalation) lands with WS5 approvals when actions can change effective authority within a session.

**Trail.** This ADR is the load-bearing reference for the WS2 OAuth implementation, the persona-switcher commit, and ADR 0042 (role-based default landing). The SSE refresh contract pinned here is the WS7 integration gate.
