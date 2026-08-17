// SPDX-License-Identifier: Apache-2.0
// POST /app/api/persona/switch — flip the active-persona pointer on a
// demo-mode session. ADR 0040 §D8 + ADR 0042 §D3.
//
// Body: {"to": "supervisor" | "analyst" | "head"}
// Requires: SBS_DEMO_MODE=true, a valid session cookie, CSRF header.
// Writes: one audit_events row with action='switch-persona',
//         meta carrying both from_persona / to_persona AND the
//         corresponding emails so the audit row reads as
//         "<operator> switched from Supervisor to Head".
// Returns: {active: "<new-key>"} on success; 400 on bad body;
//          403 on CSRF or non-demo session; 401 without session;
//          404 when SBS_DEMO_MODE is off.

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { writeAuditEvent } from '@/auth/audit';
import { authConfig } from '@/auth/config';
import { SESSION_COOKIE } from '@/auth/cookies';
import { checkCsrf } from '@/auth/csrf';
import { DEMO_PERSONAS, isDemoPersonaKey } from '@/auth/demo';
import {
  activePersona,
  getSession,
  setActivePersona,
} from '@/auth/session';

export async function POST(request: Request) {
  if (!authConfig.demoMode) {
    return new NextResponse(null, { status: 404 });
  }
  if (!checkCsrf(request)) {
    return new NextResponse(null, { status: 403 });
  }

  const sessionId = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    return new NextResponse(null, { status: 401 });
  }
  if (!session.demoMode) {
    return NextResponse.json(
      { error: 'persona switch is only available in demo-mode sessions' },
      { status: 403 },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: 'request body must be valid JSON' },
      { status: 400 },
    );
  }

  const target = (body as { to?: unknown })?.to;
  if (!isDemoPersonaKey(target)) {
    return NextResponse.json(
      { error: 'to must be one of: supervisor, analyst, head' },
      { status: 400 },
    );
  }

  if (target === session.activePersonaKey) {
    // No-op switch — no audit row.
    return NextResponse.json({ active: target });
  }

  // Capture before/after BEFORE mutating session state so audit always
  // reads the right transition even if a switch races a logout.
  const fromKey = session.activePersonaKey;
  const fromPersona = activePersona(session);
  const toPersona = session.personas[target];
  if (!toPersona) {
    return new NextResponse(null, { status: 500 });
  }

  setActivePersona(session, target);

  // The audit row carries from_persona + to_persona and the
  // corresponding emails. Per the user-facing framing
  // ("the operator switched from Supervisor to Head at 14:32"), the actor is
  // the operator name held on the session — not the persona's email.
  try {
    await writeAuditEvent({
      actor_type: 'user',
      actor_id: session.operator ?? 'demo-operator',
      action: 'switch-persona',
      object_type: 'session',
      object_id: session.id,
      meta: {
        from_persona: fromKey,
        from_email: fromPersona.email,
        from_display: DEMO_PERSONAS[fromKey as keyof typeof DEMO_PERSONAS]?.email ?? fromPersona.email,
        to_persona: target,
        to_email: toPersona.email,
      },
    });
  } catch (e) {
    // Roll back the switch on audit-write failure — the demo's
    // governance story is "every state change is audited", so a switch
    // without an audit row is worse than no switch at all.
    setActivePersona(session, fromKey);
    // eslint-disable-next-line no-console
    console.error('audit-write failed during switch-persona; reverted', e);
    return NextResponse.json(
      { error: 'audit write failed; persona switch reverted' },
      { status: 502 },
    );
  }

  return NextResponse.json({ active: target });
}
