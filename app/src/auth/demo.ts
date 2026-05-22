// Demo-mode session bootstrap — ADR 0040 §D8.
//
// In demo mode the operator (Antoine / Oumaïma at the keyboard) wants
// to switch between María / Lucía / Jorge without four sign-out
// cycles during a 15-minute regulator demo. The server pre-loads
// tokens for all three personas via the Resource Owner Password
// Credentials grant, stores them in the server-side session, and
// flips an active-persona pointer on switch.
//
// ROPC is permitted here because (a) the demo realm has seeded,
// sandbox-only passwords, (b) the feature is feature-flagged behind
// SBS_DEMO_MODE, (c) the Keycloak client's directAccessGrantsEnabled
// is off in the production overlay. RFC 9700 §2.4 carves out
// trusted-first-party use; this is the carve-out, narrowed further.

import 'server-only';

import { authConfig } from './config';
import { decodeJwtPayload, exchangePassword } from './keycloak';
import type { PersonaSession, ServerSession } from './session';

// Persona key → (email, env-var name, default password). The defaults
// match infra/keycloak/realm-sbs-demo.json so a fresh `docker compose
// up` plus a Next.js dev server work without further config; production
// overlays never reach this code (demoMode is off).
// Sandbox-only demo credentials. The default values match the seeded
// passwords in infra/keycloak/realm-sbs-demo.json. Production never
// loads this file (SBS_DEMO_MODE=false short-circuits demo-login).
// Each line carries the detect-secrets pragma because the strings are
// deliberate, sandbox-only, and committed by design.
export const DEMO_PERSONAS = {
  maria: {
    email: 'maria@sbs.gob.pe',
    passwordEnv: 'SBS_DEMO_MARIA_PASSWORD', // pragma: allowlist secret
    passwordDefault: 'maria-demo-2026', // pragma: allowlist secret
  },
  lucia: {
    email: 'lucia@sbs.gob.pe',
    passwordEnv: 'SBS_DEMO_LUCIA_PASSWORD', // pragma: allowlist secret
    passwordDefault: 'lucia-demo-2026', // pragma: allowlist secret
  },
  jorge: {
    email: 'jorge@sbs.gob.pe',
    passwordEnv: 'SBS_DEMO_JORGE_PASSWORD', // pragma: allowlist secret
    passwordDefault: 'jorge-demo-2026', // pragma: allowlist secret
  },
} as const;

export type DemoPersonaKey = keyof typeof DEMO_PERSONAS;

export const DEMO_PERSONA_KEYS: readonly DemoPersonaKey[] = ['maria', 'lucia', 'jorge'];

function passwordFor(key: DemoPersonaKey): string {
  const config = DEMO_PERSONAS[key];
  return process.env[config.passwordEnv] ?? config.passwordDefault;
}

/**
 * Acquire tokens for all three demo personas in parallel. Returns a
 * record keyed by persona key (`maria` / `lucia` / `jorge`) suitable
 * for direct assignment into the ServerSession.personas map.
 */
export async function loadAllPersonaTokens(): Promise<Record<DemoPersonaKey, PersonaSession>> {
  if (!authConfig.demoMode) {
    throw new Error(
      'loadAllPersonaTokens called outside demo mode. ' +
        'Set SBS_DEMO_MODE=true to enable.',
    );
  }

  const results = await Promise.all(
    DEMO_PERSONA_KEYS.map(async key => {
      const config = DEMO_PERSONAS[key];
      const tokens = await exchangePassword({
        username: config.email,
        password: passwordFor(key),
      });
      const payload = decodeJwtPayload(tokens.access_token);
      const now = Math.floor(Date.now() / 1000);
      const session: PersonaSession = {
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token ?? null,
        accessTokenExpiresAt: now + tokens.expires_in,
        userId: payload.sub,
        email: payload.email ?? config.email,
        displayName: payload.name ?? config.email,
        roles: payload.realm_access?.roles ?? [],
      };
      return [key, session] as const;
    }),
  );

  return Object.fromEntries(results) as Record<DemoPersonaKey, PersonaSession>;
}

/**
 * Type guard for the persona key submitted on the switcher endpoint.
 * Anything outside the seeded set is rejected at the boundary.
 */
export function isDemoPersonaKey(value: unknown): value is DemoPersonaKey {
  return typeof value === 'string' && (DEMO_PERSONA_KEYS as readonly string[]).includes(value);
}
