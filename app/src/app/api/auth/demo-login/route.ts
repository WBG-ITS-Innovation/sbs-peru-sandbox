// SPDX-License-Identifier: Apache-2.0
// GET /app/api/auth/demo-login — demo-mode bootstrap. Acquires tokens
// for all three demo personas via ROPC, builds a server-side session,
// writes one audit row, redirects to María's landing route (cockpit).
//
// Feature-flagged behind SBS_DEMO_MODE. Returns 404 when off so a
// production deployment never exposes a clickable demo-login surface.
//
// Optional ?operator=<name> query param sets the audit actor for
// subsequent persona switches. Default: "demo-operator".

import { NextResponse } from 'next/server';

import { writeAuditEvent } from '@/auth/audit';
import { authConfig } from '@/auth/config';
import {
  CSRF_COOKIE,
  SESSION_COOKIE,
  csrfCookieOptions,
  sessionCookieOptions,
} from '@/auth/cookies';
import { DEMO_PERSONAS, loadAllPersonaTokens } from '@/auth/demo';
import { landingRouteForRoles } from '@/auth/landing';
import { generateCsrfToken, generateSessionId } from '@/auth/pkce';
import { createSession } from '@/auth/session';

const APP_BASE_PATH = '/app';

export async function GET(request: Request) {
  if (!authConfig.demoMode) {
    return new NextResponse(null, { status: 404 });
  }

  const url = new URL(request.url);
  const operator = (url.searchParams.get('operator') ?? 'demo-operator').slice(0, 64);

  let personas;
  try {
    personas = await loadAllPersonaTokens();
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('demo-login: ROPC failed loading persona tokens', e);
    return NextResponse.redirect(
      new URL(`${APP_BASE_PATH}/login?error=demo_login_failed`, request.url),
    );
  }

  const sessionId = generateSessionId();
  const csrfToken = generateCsrfToken();
  const now = Math.floor(Date.now() / 1000);

  createSession({
    id: sessionId,
    activePersonaKey: 'maria',
    csrfToken,
    createdAt: now,
    lastActivityAt: now,
    demoMode: true,
    operator,
    locale: null,
    personas,
  });

  // Audit the demo-mode entry. The actor is the operator name (e.g.,
  // "the operator"); meta carries the loaded personas so an auditor reading
  // the row knows what set of identities the session can switch
  // between.
  const initialRoles = personas.maria.roles;
  const landing = landingRouteForRoles(initialRoles);
  try {
    await writeAuditEvent({
      actor_type: 'user',
      actor_id: operator,
      action: 'demo-login',
      object_type: 'session',
      object_id: sessionId,
      meta: {
        loaded_personas: Object.keys(DEMO_PERSONAS),
        initial_persona: 'maria',
        landed_at: landing,
      },
    });
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error('audit-write failed during demo-login', e);
  }

  const response = NextResponse.redirect(
    new URL(`${APP_BASE_PATH}${landing}`, request.url),
  );
  response.cookies.set(SESSION_COOKIE, sessionId, sessionCookieOptions());
  response.cookies.set(CSRF_COOKIE, csrfToken, csrfCookieOptions());
  return response;
}
