// Keycloak token-endpoint client. Wraps the three exchanges we need:
// authorization_code (real login), refresh_token (silent refresh — WS7
// SSE), and password (demo-mode persona switcher only, ADR 0040 §D8).
//
// Token verification — for the demo we trust the access token because
// it came directly from Keycloak's token endpoint over a server-to-
// server connection. Production should verify the JWT signature
// against Keycloak's JWKS; that's a Part 9 hardening item.

import 'server-only';

import { authConfig, oidcEndpoints } from './config';

export interface TokenResponse {
  access_token: string;
  refresh_token?: string;
  expires_in: number;
  refresh_expires_in?: number;
  token_type: string;
  id_token?: string;
  scope?: string;
}

export interface DecodedToken {
  sub: string;
  email?: string;
  email_verified?: boolean;
  preferred_username?: string;
  name?: string;
  given_name?: string;
  family_name?: string;
  realm_access?: { roles?: string[] };
  exp: number;
  iat: number;
}

/**
 * Exchange an authorization code for a token set (Authorization Code
 * with PKCE — RFC 6749 §4.1 + RFC 7636 §4.5).
 */
export async function exchangeAuthorizationCode(args: {
  code: string;
  codeVerifier: string;
}): Promise<TokenResponse> {
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: authConfig.clientId,
    code: args.code,
    redirect_uri: authConfig.redirectUri,
    code_verifier: args.codeVerifier,
  });
  return postToken(body);
}

/**
 * Exchange username/password for a token set (Resource Owner Password
 * Credentials — RFC 6749 §4.3). Demo-mode only (ADR 0040 §D8). The
 * caller MUST verify demoMode is enabled before calling.
 */
export async function exchangePassword(args: {
  username: string;
  password: string;
}): Promise<TokenResponse> {
  if (!authConfig.demoMode) {
    throw new Error('Password grant is only available in demo mode.');
  }
  const body = new URLSearchParams({
    grant_type: 'password',
    client_id: authConfig.clientId,
    username: args.username,
    password: args.password,
    scope: 'openid profile email',
  });
  return postToken(body);
}

/**
 * Refresh an access token (RFC 6749 §6). Used by the silent-refresh
 * path; the WS7 SSE reconnect calls into this.
 */
export async function refreshAccessToken(refreshToken: string): Promise<TokenResponse> {
  const body = new URLSearchParams({
    grant_type: 'refresh_token',
    client_id: authConfig.clientId,
    refresh_token: refreshToken,
  });
  return postToken(body);
}

/**
 * Decode (but do NOT verify) a JWT payload. Used to extract the roles
 * claim immediately after a token exchange; the token came from the
 * Keycloak token endpoint over TLS so the trust assumption is bounded.
 * Production verifies the signature against JWKS — Part 9.
 */
export function decodeJwtPayload(token: string): DecodedToken {
  const parts = token.split('.');
  if (parts.length !== 3) {
    throw new Error('Malformed JWT (expected three dot-separated segments)');
  }
  const payload = Buffer.from(parts[1].replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf-8');
  return JSON.parse(payload) as DecodedToken;
}

async function postToken(body: URLSearchParams): Promise<TokenResponse> {
  const response = await fetch(oidcEndpoints.token(), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'application/json',
    },
    body: body.toString(),
    // Server-to-server only — never proxied through a browser.
    cache: 'no-store',
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Token endpoint returned ${response.status}: ${text}`);
  }
  return (await response.json()) as TokenResponse;
}

/**
 * Build the Keycloak `/auth` URL for the Authorization Code flow.
 * Caller already has the PKCE verifier; this returns the URL the user
 * should be redirected to.
 */
export function buildAuthorizationUrl(args: {
  state: string;
  codeChallenge: string;
  scope?: string;
}): string {
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: authConfig.clientId,
    redirect_uri: authConfig.redirectUri,
    state: args.state,
    code_challenge: args.codeChallenge,
    code_challenge_method: 'S256',
    scope: args.scope ?? 'openid profile email',
  });
  return `${oidcEndpoints.authorize()}?${params.toString()}`;
}

/**
 * Build the Keycloak logout URL. Keycloak 22+ requires id_token_hint
 * or client_id+post_logout_redirect_uri.
 */
export function buildLogoutUrl(args: { idToken?: string }): string {
  const params = new URLSearchParams({
    post_logout_redirect_uri: authConfig.postLogoutRedirectUri,
    client_id: authConfig.clientId,
  });
  if (args.idToken) {
    params.set('id_token_hint', args.idToken);
  }
  return `${oidcEndpoints.logout()}?${params.toString()}`;
}
