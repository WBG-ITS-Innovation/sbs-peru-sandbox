// SPDX-License-Identifier: Apache-2.0
// Next.js proxy: POST /app/api/findings/:id/draft → FastAPI
// /v1/internal/findings/:id/draft. The browser submits with the
// session cookie + CSRF header; the server validates the session,
// resolves the active persona's identity + roles, and forwards.

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { authConfig } from '@/auth/config';
import { SESSION_COOKIE } from '@/auth/cookies';
import { checkCsrf } from '@/auth/csrf';
import { activePersona, getSession } from '@/auth/session';

export async function POST(request: Request, props: { params: Promise<{ id: string }> }) {
  const params = await props.params;
  if (!checkCsrf(request)) {
    return new NextResponse(null, { status: 403 });
  }
  const sessionId = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    return new NextResponse(null, { status: 401 });
  }
  const persona = activePersona(session);

  let body: { after_text?: string; agent_run_id?: string | null };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 });
  }
  if (typeof body.after_text !== 'string') {
    return NextResponse.json({ error: 'missing_after_text' }, { status: 400 });
  }

  const upstream = await fetch(
    `${authConfig.internalApiBaseUrl}/v1/internal/findings/${encodeURIComponent(params.id)}/draft`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${authConfig.internalApiSecret()}`,
        'X-SBS-Role': persona.roles.join(','),
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        after_text: body.after_text,
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
