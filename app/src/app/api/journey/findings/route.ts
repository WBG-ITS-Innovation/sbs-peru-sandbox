// SPDX-License-Identifier: Apache-2.0
// GET /app/api/journey/findings?complaint_id=<id>
//
// Stage 5 of the demo-journey overlay. Server-to-server proxy to the
// FastAPI finding-detail endpoint. Returns the raw payload (agent_runs
// included) for the client component to render.

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { authConfig } from '@/auth/config';
import { SESSION_COOKIE } from '@/auth/cookies';
import { activePersona, getSession } from '@/auth/session';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function GET(request: Request) {
  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    return NextResponse.json({ error: 'unauthenticated' }, { status: 401 });
  }
  const persona = activePersona(session);
  if (persona.roles.length === 0) {
    return NextResponse.json({ error: 'no_role' }, { status: 403 });
  }

  const url = new URL(request.url);
  const complaintId = url.searchParams.get('complaint_id');
  if (!complaintId) {
    return NextResponse.json({ error: 'complaint_id required' }, { status: 400 });
  }

  const upstream = await fetch(
    `${authConfig.internalApiBaseUrl}/v1/internal/findings/${encodeURIComponent(complaintId)}`,
    {
      headers: {
        Authorization: `Bearer ${authConfig.internalApiSecret()}`,
        'X-SBS-Role': persona.roles.join(','),
      },
      cache: 'no-store',
    },
  );
  if (upstream.status === 404) {
    return NextResponse.json({}, { status: 404 });
  }
  if (!upstream.ok) {
    return NextResponse.json(
      { error: `upstream ${upstream.status}` },
      { status: upstream.status },
    );
  }
  const json = await upstream.json();
  return NextResponse.json(json);
}
