// SPDX-License-Identifier: Apache-2.0
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { landingRouteForRoles } from '@/auth/landing';
import { activePersona, getSession } from '@/auth/session';
import { SESSION_COOKIE } from '@/auth/cookies';

// /app/ — the entry point of the supervisor UI.
// - Unauthenticated → redirect to /app/login.
// - Authenticated → role-based landing per ADR 0042 D1.
//
// The redirect happens server-side, so the user never sees a flash of
// an intermediate page.
export default function RootPage() {
  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);

  if (!session) {
    redirect('/login');
  }

  const persona = activePersona(session);
  redirect(landingRouteForRoles(persona.roles));
}
