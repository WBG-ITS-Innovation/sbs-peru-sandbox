// SPDX-License-Identifier: Apache-2.0
// Cookie names and flags. One module so renaming a cookie is a
// single-file change and the rest of the auth layer never spells out a
// raw cookie name.

import 'server-only';

import type { ResponseCookie } from 'next/dist/compiled/@edge-runtime/cookies';

// The opaque session id. HttpOnly so JS cannot read it; SameSite=Lax so
// it survives top-level navigation but not cross-site POST. Path=/ so
// the cookie reaches every supervisor-UI route. Secure in production
// (set via env detection below).
export const SESSION_COOKIE = 'sbs-session';

// CSRF double-submit pair (ADR 0040 §D4). Cookie is NOT HttpOnly so the
// JS client can read it and copy the value into the X-SBS-CSRF header
// on state-changing requests. Cookie and header must match.
export const CSRF_COOKIE = 'sbs-csrf';
export const CSRF_HEADER = 'x-sbs-csrf';

// Locale toggle. NOT HttpOnly because client-side language toggle reads
// it for immediate UI feedback before the server round-trip.
export const LOCALE_COOKIE = 'sbs-locale';

// PKCE + state pair held between the /api/auth/login redirect and the
// /api/auth/callback exchange. HttpOnly, short TTL, deleted after use.
export const OAUTH_TRANSIENT_COOKIE = 'sbs-oauth-state';

const isProd = process.env.NODE_ENV === 'production';

export function sessionCookieOptions(): Partial<ResponseCookie> {
  return {
    httpOnly: true,
    secure: isProd,
    sameSite: 'lax',
    path: '/',
  };
}

export function csrfCookieOptions(): Partial<ResponseCookie> {
  return {
    httpOnly: false, // Client must read this for the X-SBS-CSRF header.
    secure: isProd,
    sameSite: 'lax',
    path: '/',
  };
}

export function localeCookieOptions(): Partial<ResponseCookie> {
  return {
    httpOnly: false,
    secure: isProd,
    sameSite: 'lax',
    path: '/',
    // One year — locale is a sticky preference, not a session affordance.
    maxAge: 60 * 60 * 24 * 365,
  };
}

export function oauthTransientCookieOptions(): Partial<ResponseCookie> {
  return {
    httpOnly: true,
    secure: isProd,
    sameSite: 'lax',
    path: '/',
    // 10 minutes — long enough for a slow IdP round-trip, short enough
    // that a stalled login does not leave a stale verifier in the
    // browser.
    maxAge: 60 * 10,
  };
}
