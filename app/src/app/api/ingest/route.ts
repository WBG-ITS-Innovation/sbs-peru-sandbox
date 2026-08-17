// SPDX-License-Identifier: Apache-2.0
// Next.js proxy: POST /app/api/ingest → FastAPI
// /v1/internal/demo/simulate-submission. The browser submits a
// realistic Anexo-1A-shaped complaint with PII fields (sandbox demo
// only); the FastAPI endpoint redacts, persists, audits, and
// publishes the SSE delta. The shared internal secret never reaches
// the browser.
//
// Authentication: session cookie + CSRF header + active-persona
// roles. Only authenticated supervisors can trigger the demo
// ingestion path.

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { authConfig } from '@/auth/config';
import { SESSION_COOKIE } from '@/auth/cookies';
import { checkCsrf } from '@/auth/csrf';
import { activePersona, getSession } from '@/auth/session';

export async function POST(request: Request) {
  if (!checkCsrf(request)) {
    return new NextResponse(null, { status: 403 });
  }
  const sessionId = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    return new NextResponse(null, { status: 401 });
  }
  const persona = activePersona(session);
  if (persona.roles.length === 0) {
    return new NextResponse(null, { status: 403 });
  }

  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 });
  }

  const upstream = await fetch(
    `${authConfig.internalApiBaseUrl}/v1/internal/demo/simulate-submission`,
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
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') ?? 'application/json',
    },
  });
}
