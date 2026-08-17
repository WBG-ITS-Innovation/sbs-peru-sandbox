// SPDX-License-Identifier: Apache-2.0
// CSRF double-submit cookie pattern — ADR 0040 §D4. Every state-
// changing request carries the session cookie (automatic) and an
// X-SBS-CSRF header whose value matches the sbs-csrf cookie. The
// middleware rejects mismatches.

import 'server-only';

import { CSRF_COOKIE, CSRF_HEADER } from './cookies';

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

/**
 * Check the CSRF header against the cookie. Returns true on a safe
 * method or a matching pair; false on a state-changing method whose
 * header is missing or does not match.
 */
export function checkCsrf(request: Request): boolean {
  if (SAFE_METHODS.has(request.method)) return true;

  // Read the cookie from the request header rather than via next/headers
  // so this helper works in middleware and edge runtimes too.
  const cookieValue = readCookie(request, CSRF_COOKIE);
  const headerValue = request.headers.get(CSRF_HEADER);
  if (!cookieValue || !headerValue) return false;
  return constantTimeEqual(cookieValue, headerValue);
}

function readCookie(request: Request, name: string): string | null {
  const header = request.headers.get('cookie');
  if (!header) return null;
  for (const part of header.split(';')) {
    const trimmed = part.trim();
    const eq = trimmed.indexOf('=');
    if (eq === -1) continue;
    if (trimmed.slice(0, eq) === name) {
      return decodeURIComponent(trimmed.slice(eq + 1));
    }
  }
  return null;
}

function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}
