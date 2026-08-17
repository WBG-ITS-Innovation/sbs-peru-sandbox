// SPDX-License-Identifier: Apache-2.0
// PKCE helpers — RFC 7636. Used by the OAuth login flow to prove
// possession of the code_verifier without ever putting it in the
// authorization request.

import 'server-only';

import { randomBytes, createHash } from 'node:crypto';

/**
 * Generate a code_verifier per RFC 7636 §4.1. 43-128 characters from
 * the URL-safe alphabet. We use 64 random bytes → 86 char base64url.
 */
export function generateCodeVerifier(): string {
  return base64UrlEncode(randomBytes(64));
}

/**
 * Generate the code_challenge for the S256 method per RFC 7636 §4.2.
 * The challenge is sent to the authorization endpoint; the verifier is
 * sent to the token endpoint.
 */
export function codeChallengeS256(verifier: string): string {
  return base64UrlEncode(createHash('sha256').update(verifier).digest());
}

/**
 * Generate a random state value (RFC 6749 §10.12). Bound to the
 * session-creation flow so a cross-site forgery cannot induce a code
 * acceptance from a flow the user never initiated.
 */
export function generateState(): string {
  return base64UrlEncode(randomBytes(32));
}

/**
 * Generate an opaque session id. Cryptographically random, base64url,
 * 32 bytes of entropy.
 */
export function generateSessionId(): string {
  return base64UrlEncode(randomBytes(32));
}

/**
 * Generate a CSRF token. Same shape as the session id — random,
 * opaque, URL-safe.
 */
export function generateCsrfToken(): string {
  return base64UrlEncode(randomBytes(32));
}

function base64UrlEncode(buf: Buffer): string {
  return buf.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
