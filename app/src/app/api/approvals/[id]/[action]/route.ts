// SPDX-License-Identifier: Apache-2.0
// Proxy: POST /app/api/approvals/:id/:action → FastAPI's
// /v1/internal/approvals/:id/:action. One route handler covers all
// four actions; the action is validated against an allowlist before
// forwarding.

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { authConfig } from '@/auth/config';
import { SESSION_COOKIE } from '@/auth/cookies';
import { checkCsrf } from '@/auth/csrf';
import { activePersona, getSession } from '@/auth/session';

const ALLOWED_ACTIONS = new Set([
  'approve',
  'approve-with-edits',
  'reject',
  'send-back',
]);

export async function POST(
  request: Request,
  props: { params: Promise<{ id: string; action: string }> }
) {
  const params = await props.params;
  if (!ALLOWED_ACTIONS.has(params.action)) {
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
  const persona = activePersona(session);

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    body = {};
  }
  // The FastAPI side expects actor_id on every action.
  body.actor_id = persona.email;

  const upstream = await fetch(
    `${authConfig.internalApiBaseUrl}/v1/internal/approvals/${encodeURIComponent(params.id)}/${encodeURIComponent(params.action)}`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authConfig.internalApiSecret()}`,
        'X-SBS-Role': persona.roles.join(','),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      cache: 'no-store',
    },
  );
  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { 'Content-Type': upstream.headers.get('Content-Type') ?? 'application/json' },
  });
}
