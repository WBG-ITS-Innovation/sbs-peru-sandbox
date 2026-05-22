// POST /app/api/auth/logout — destroy the server-side session and
// redirect to Keycloak's end-session endpoint. POST so this is not
// triggered by a stray <a href> click; the logout button in the nav
// rail (WS1) issues a form POST with the CSRF header.

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { writeAuditEvent } from '@/auth/audit';
import { checkCsrf } from '@/auth/csrf';
import { CSRF_COOKIE, SESSION_COOKIE } from '@/auth/cookies';
import { buildLogoutUrl } from '@/auth/keycloak';
import { activePersona, destroySession, getSession } from '@/auth/session';

export async function POST(request: Request) {
  if (!checkCsrf(request)) {
    return new NextResponse(null, { status: 403 });
  }

  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);

  // Record the logout BEFORE destroying the session — the audit row
  // names the actor.
  if (session) {
    try {
      const persona = activePersona(session);
      await writeAuditEvent({
        actor_type: 'user',
        actor_id: persona.email,
        action: 'logout',
        object_type: 'session',
        object_id: session.id,
      });
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('audit-write failed during logout', e);
    }
  }

  destroySession(sessionId);

  const response = NextResponse.redirect(
    buildLogoutUrl({}),
    { status: 303 }, // POST → GET handoff to Keycloak's end-session endpoint
  );
  response.cookies.delete(SESSION_COOKIE);
  response.cookies.delete(CSRF_COOKIE);
  return response;
}
