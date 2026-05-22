// Server-side session store — ADR 0040 §D3. Opaque session ids keyed
// to an in-process Map; tokens never reach the browser. Production
// migrates the backend to Redis under SBS_SESSION_BACKEND=redis; the
// interface here does not change.
//
// The Map is held on globalThis so Next.js dev-mode HMR does not blow
// it away on every save — which would log every user out on every code
// change.

import 'server-only';

import type { Locale } from '@/i18n';

export type Persona = 'maria' | 'lucia' | 'jorge';

export interface PersonaSession {
  readonly accessToken: string;
  readonly refreshToken: string | null;
  readonly accessTokenExpiresAt: number; // epoch seconds
  readonly userId: string;                // Keycloak `sub`
  readonly email: string;
  readonly displayName: string;
  readonly roles: readonly string[];      // realm-roles claim
}

export interface ServerSession {
  readonly id: string;
  // Demo-mode sessions carry tokens for all three personas; standard
  // sessions carry one token under the operator's own identity (keyed
  // by the operator's email, not by a persona enum).
  readonly personas: Readonly<Record<string, PersonaSession>>;
  activePersonaKey: string;
  readonly csrfToken: string;
  readonly createdAt: number;             // epoch seconds
  lastActivityAt: number;
  readonly demoMode: boolean;
  // Locale preference can also live in a cookie; the session copy is
  // authoritative when both are present, so a server-action language
  // switch survives a cookie wipe.
  locale: Locale | null;
}

declare global {
  // eslint-disable-next-line no-var
  var __sbsSessionStore: Map<string, ServerSession> | undefined;
}

function store(): Map<string, ServerSession> {
  if (!globalThis.__sbsSessionStore) {
    globalThis.__sbsSessionStore = new Map<string, ServerSession>();
  }
  return globalThis.__sbsSessionStore;
}

export function createSession(session: ServerSession): void {
  store().set(session.id, session);
}

export function getSession(id: string | undefined | null): ServerSession | null {
  if (!id) return null;
  const s = store().get(id);
  if (!s) return null;
  // Lazy expiry: drop the session if its access token expired more
  // than 24h ago. WS7 silent refresh handles in-window expiry; this is
  // the floor for abandoned sessions.
  const now = Math.floor(Date.now() / 1000);
  const dayAgo = now - 60 * 60 * 24;
  if (s.lastActivityAt < dayAgo) {
    store().delete(id);
    return null;
  }
  s.lastActivityAt = now;
  return s;
}

export function destroySession(id: string | undefined | null): void {
  if (!id) return;
  store().delete(id);
}

export function activePersona(session: ServerSession): PersonaSession {
  const p = session.personas[session.activePersonaKey];
  if (!p) {
    throw new Error(
      `Session ${session.id} has no persona under key ${session.activePersonaKey}`,
    );
  }
  return p;
}

export function setActivePersona(session: ServerSession, key: string): void {
  if (!session.personas[key]) {
    throw new Error(`Cannot switch to unknown persona key: ${key}`);
  }
  session.activePersonaKey = key;
}
