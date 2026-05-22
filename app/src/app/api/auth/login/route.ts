// GET /app/api/auth/login — start the OAuth Authorization Code with PKCE
// flow. Generate state + verifier, set a short-lived HttpOnly cookie
// holding both, redirect to Keycloak.

import { NextResponse } from 'next/server';

import { OAUTH_TRANSIENT_COOKIE, oauthTransientCookieOptions } from '@/auth/cookies';
import { buildAuthorizationUrl } from '@/auth/keycloak';
import {
  codeChallengeS256,
  generateCodeVerifier,
  generateState,
} from '@/auth/pkce';

export async function GET() {
  const codeVerifier = generateCodeVerifier();
  const state = generateState();

  const authorizationUrl = buildAuthorizationUrl({
    state,
    codeChallenge: codeChallengeS256(codeVerifier),
  });

  const response = NextResponse.redirect(authorizationUrl);
  response.cookies.set(OAUTH_TRANSIENT_COOKIE, JSON.stringify({ codeVerifier, state }), {
    ...oauthTransientCookieOptions(),
  });
  return response;
}
