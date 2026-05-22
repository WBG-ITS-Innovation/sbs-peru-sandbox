// Next.js proxy: POST /app/api/findings/:id/send-to-approvals →
// FastAPI /v1/internal/findings/:id/send-to-approvals.

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { authConfig } from '@/auth/config';
import { SESSION_COOKIE } from '@/auth/cookies';
import { checkCsrf } from '@/auth/csrf';
import { activePersona, getSession } from '@/auth/session';

export async function POST(
  request: Request,
  { params }: { params: { id: string } },
) {
  if (!checkCsrf(request)) {
    return new NextResponse(null, { status: 403 });
  }
  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    return new NextResponse(null, { status: 401 });
  }
  const persona = activePersona(session);

  let body: { severity?: string; agent_run_id?: string | null };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 });
  }
  const allowedSeverities = ['low', 'medium', 'high', 'critical'];
  if (!body.severity || !allowedSeverities.includes(body.severity)) {
    return NextResponse.json({ error: 'invalid_severity' }, { status: 400 });
  }

  const upstream = await fetch(
    `${authConfig.internalApiBaseUrl}/v1/internal/findings/${encodeURIComponent(params.id)}/send-to-approvals`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authConfig.internalApiSecret()}`,
        'X-SBS-Role': persona.roles.join(','),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        severity: body.severity,
        actor_id: persona.email,
        agent_run_id: body.agent_run_id ?? null,
      }),
      cache: 'no-store',
    },
  );

  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { 'Content-Type': upstream.headers.get('Content-Type') ?? 'application/json' },
  });
}
