// GET /app/api/auth/callback — Keycloak redirects here after the user
// signs in. Exchange the code for tokens, build the server-side session,
// write one audit row, redirect to the role-based landing route.

import { NextResponse } from 'next/server';

import { writeAuditEvent } from '@/auth/audit';
import {
  CSRF_COOKIE,
  OAUTH_TRANSIENT_COOKIE,
  SESSION_COOKIE,
  csrfCookieOptions,
  oauthTransientCookieOptions,
  sessionCookieOptions,
} from '@/auth/cookies';
import { decodeJwtPayload, exchangeAuthorizationCode } from '@/auth/keycloak';
import { landingRouteForRoles } from '@/auth/landing';
import { generateCsrfToken, generateSessionId } from '@/auth/pkce';
import { createSession } from '@/auth/session';

const APP_BASE_PATH = '/app';

export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get('code');
  const stateParam = url.searchParams.get('state');
  const errorParam = url.searchParams.get('error');

  if (errorParam) {
    return NextResponse.redirect(
      new URL(`${APP_BASE_PATH}/login?error=${encodeURIComponent(errorParam)}`, request.url),
    );
  }
  if (!code || !stateParam) {
    return NextResponse.redirect(
      new URL(`${APP_BASE_PATH}/login?error=missing_code_or_state`, request.url),
    );
  }

  // Recover the PKCE verifier + state from the transient cookie.
  const transientCookie = request.headers
    .get('cookie')
    ?.split(';')
    .map(s => s.trim())
    .find(s => s.startsWith(`${OAUTH_TRANSIENT_COOKIE}=`));
  if (!transientCookie) {
    return NextResponse.redirect(
      new URL(`${APP_BASE_PATH}/login?error=session_expired`, request.url),
    );
  }
  let transient: { codeVerifier: string; state: string };
  try {
    const value = decodeURIComponent(transientCookie.split('=')[1]);
    transient = JSON.parse(value);
  } catch {
    return NextResponse.redirect(
      new URL(`${APP_BASE_PATH}/login?error=invalid_state`, request.url),
    );
  }

  if (transient.state !== stateParam) {
    return NextResponse.redirect(
      new URL(`${APP_BASE_PATH}/login?error=state_mismatch`, request.url),
    );
  }

  // Exchange code for tokens.
  let tokens;
  try {
    tokens = await exchangeAuthorizationCode({
      code,
      codeVerifier: transient.codeVerifier,
    });
  } catch (e) {
    return NextResponse.redirect(
      new URL(`${APP_BASE_PATH}/login?error=token_exchange_failed`, request.url),
    );
  }

  // Decode the access token to extract identity + roles. Trust without
  // verifying signature — token came over server-to-server TLS from
  // Keycloak's token endpoint. Part 9 hardens this with JWKS check.
  const payload = decodeJwtPayload(tokens.access_token);
  const roles = payload.realm_access?.roles ?? [];
  const userKey = payload.email ?? payload.preferred_username ?? payload.sub;

  // Build the session. One persona at standard login (not demo mode).
  const sessionId = generateSessionId();
  const csrfToken = generateCsrfToken();
  const now = Math.floor(Date.now() / 1000);

  createSession({
    id: sessionId,
    activePersonaKey: userKey,
    csrfToken,
    createdAt: now,
    lastActivityAt: now,
    demoMode: false,
    locale: null,
    personas: {
      [userKey]: {
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token ?? null,
        accessTokenExpiresAt: now + tokens.expires_in,
        userId: payload.sub,
        email: payload.email ?? userKey,
        displayName: payload.name ?? userKey,
        roles,
      },
    },
  });

  // Audit the login. Captures the landing decision (ADR 0042 §D4).
  const landing = landingRouteForRoles(roles);
  try {
    await writeAuditEvent({
      actor_type: 'user',
      actor_id: payload.email ?? userKey,
      action: 'login',
      object_type: 'session',
      object_id: sessionId,
      meta: { roles, landed_at: landing },
    });
  } catch (e) {
    // Don't fail login on audit-write failure — but log loudly so an
    // operational alert fires. The decision lands in production-readiness
    // (Part 9): is the audit chain a hard gate or a best-effort sidecar?
    // Today: best-effort with visible logging.
    // eslint-disable-next-line no-console
    console.error('audit-write failed during login callback', e);
  }

  const response = NextResponse.redirect(
    new URL(`${APP_BASE_PATH}${landing}`, request.url),
  );
  response.cookies.set(SESSION_COOKIE, sessionId, sessionCookieOptions());
  response.cookies.set(CSRF_COOKIE, csrfToken, csrfCookieOptions());
  response.cookies.delete(OAUTH_TRANSIENT_COOKIE);
  return response;
}
