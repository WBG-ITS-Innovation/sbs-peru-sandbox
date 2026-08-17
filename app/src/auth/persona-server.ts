// SPDX-License-Identifier: Apache-2.0
// Server-only persona helpers for the demo dashboards (P-RESHAPE-10).
//
// The active persona lives in a cookie set by the /login picker. Every
// internal call is made server-side with the shared secret in the
// Authorization header and `X-SBS-Role` derived from the cookie — never
// from the URL — so persona scoping is enforced by the backend and a
// caller cannot widen their own role. The secret never reaches the
// browser.

import 'server-only';

import { cookies } from 'next/headers';

import { authConfig } from '@/auth/config';
import { internalGet } from '@/lib/api';
import { PERSONAS, isPersonaSlug, type PersonaConfig } from '@/lib/persona';

export const PERSONA_COOKIE = 'sbs_demo_persona';

export function personaCookieOptions() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
    maxAge: 60 * 60 * 8, // an 8-hour demo day
  };
}

export async function activePersona(): Promise<PersonaConfig | null> {
  const slug = (await cookies()).get(PERSONA_COOKIE)?.value;
  return isPersonaSlug(slug) ? PERSONAS[slug] : null;
}

export function personaGet<T>(
  persona: PersonaConfig,
  path: string,
  opts?: { asUser?: boolean },
): Promise<T> {
  if (opts?.asUser) {
    return rawGet<T>(persona, path);
  }
  return internalGet<T>(path, { roles: [persona.role] });
}

async function rawGet<T>(persona: PersonaConfig, path: string): Promise<T> {
  const res = await fetch(`${authConfig.internalApiBaseUrl}${path}`, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${authConfig.internalApiSecret()}`,
      Accept: 'application/json',
      'X-SBS-Role': persona.role,
      'X-SBS-User': persona.chatUserId,
    },
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`personaGet ${path} returned ${res.status}`);
  }
  return (await res.json()) as T;
}

/** GET that returns `fallback` on any error, so one dead endpoint does
 *  not blank an entire dashboard. */
export async function safeGet<T>(
  persona: PersonaConfig,
  path: string,
  fallback: T,
  opts?: { asUser?: boolean },
): Promise<T> {
  try {
    return await personaGet<T>(persona, path, opts);
  } catch {
    return fallback;
  }
}

export interface PersonaPostResult {
  ok: boolean;
  status: number;
  data: unknown;
}

export async function personaPost(
  persona: PersonaConfig,
  path: string,
  body: unknown,
  opts?: { asUser?: boolean },
): Promise<PersonaPostResult> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${authConfig.internalApiSecret()}`,
    Accept: 'application/json',
    'Content-Type': 'application/json',
    'X-SBS-Role': persona.role,
  };
  if (opts?.asUser) {
    headers['X-SBS-User'] = persona.chatUserId;
  }
  const res = await fetch(`${authConfig.internalApiBaseUrl}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body ?? {}),
    cache: 'no-store',
  });
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  return { ok: res.ok, status: res.status, data };
}
