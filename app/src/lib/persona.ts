// SPDX-License-Identifier: Apache-2.0
// Demo persona registry — the single source of truth that maps a
// dashboard route slug to its backend role string, the seeded user ids,
// and the bilingual labels. Pure module (no next/headers, no secrets) so
// it is safe to import from both server and client components.
//
// This is the DEMO path (P-RESHAPE-10). The browser never holds the
// shared secret; the Next.js server attaches `X-SBS-Role` derived from
// the active persona cookie on every internal call, exactly as the
// production Keycloak BFF does. The role strings below match
// api/sbs_api/auth/persona_scopes.py.

export type PersonaSlug =
  | 'conduct_analyst'
  | 'conduct_supervisor'
  | 'conduct_unit_head'
  | 'superintendent'
  | 'sbs_it';

export interface PersonaConfig {
  readonly slug: PersonaSlug;
  /** X-SBS-Role value the backend scopes on. */
  readonly role: string;
  /** Bare username the cockpit task queues key on (seed_demo.py). */
  readonly taskUserId: string;
  /** Email the chatbot session binds to (X-SBS-User). */
  readonly chatUserId: string;
  readonly name: string;
  readonly titleEs: string;
  readonly titleEn: string;
  /** Rosa's chatbot is ops-only and deferred (P-RESHAPE-10 scope note). */
  readonly hasChatbot: boolean;
}

export const PERSONAS: Record<PersonaSlug, PersonaConfig> = {
  conduct_analyst: {
    slug: 'conduct_analyst',
    role: 'sbs:conduct:analyst',
    taskUserId: 'lucia',
    chatUserId: 'lucia@sandbox.example.com',
    name: 'Lucía',
    titleEs: 'Analista de Conducta',
    titleEn: 'Conduct Analyst',
    hasChatbot: true,
  },
  conduct_supervisor: {
    slug: 'conduct_supervisor',
    role: 'sbs:conduct:supervisor',
    taskUserId: 'maria',
    chatUserId: 'maria@sandbox.example.com',
    name: 'María',
    titleEs: 'Supervisora de Conducta',
    titleEn: 'Conduct Supervisor',
    hasChatbot: true,
  },
  conduct_unit_head: {
    slug: 'conduct_unit_head',
    role: 'sbs:conduct:head',
    taskUserId: 'jorge',
    chatUserId: 'jorge@sandbox.example.com',
    name: 'Jorge',
    titleEs: 'Jefe de Unidad de Conducta',
    titleEn: 'Conduct Unit Head',
    hasChatbot: true,
  },
  superintendent: {
    slug: 'superintendent',
    role: 'sbs:superintendent',
    taskUserId: 'sergio',
    chatUserId: 'sergio@sandbox.example.com',
    name: 'Sergio',
    titleEs: 'Superintendente',
    titleEn: 'Superintendent',
    hasChatbot: true,
  },
  sbs_it: {
    slug: 'sbs_it',
    role: 'sbs:sbs_it',
    taskUserId: 'rosa',
    chatUserId: 'rosa@sandbox.example.com',
    name: 'Rosa',
    titleEs: 'TI de la SBS',
    titleEn: 'SBS IT',
    hasChatbot: false,
  },
};

export const PERSONA_SLUGS = Object.keys(PERSONAS) as PersonaSlug[];

export function isPersonaSlug(value: unknown): value is PersonaSlug {
  return typeof value === 'string' && value in PERSONAS;
}

export function personaTitle(p: PersonaConfig, locale: string): string {
  return locale.startsWith('es') ? p.titleEs : p.titleEn;
}

// FI-facing agent character avatars — letter placeholders on WBG navy
// (#002244) until real artwork lands (deferred per P-RESHAPE-10 scope).
export const AGENT_AVATARS: Record<string, { initials: string }> = {
  divalevale: { initials: 'DV' },
  reclamito: { initials: 'R' },
  lupaman: { initials: 'L' },
};
