// SPDX-License-Identifier: Apache-2.0
// GET /app/api/journey/audit?object_id=<id>
//
// Stage 4 of the demo-journey overlay. Server-to-server proxy to the
// FastAPI internal audit endpoint, scoped to one complaint's events.
//
// Returns { events: AuditEvent[] }. We page through with page_size=100;
// the demo doesn't need more, and 100 audit rows comfortably covers a
// single complaint's full chain.

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { authConfig } from '@/auth/config';
import { SESSION_COOKIE } from '@/auth/cookies';
import { activePersona, getSession } from '@/auth/session';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function GET(request: Request) {
  const sessionId = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    return NextResponse.json({ error: 'unauthenticated' }, { status: 401 });
  }
  const persona = activePersona(session);
  if (persona.roles.length === 0) {
    return NextResponse.json({ error: 'no_role' }, { status: 403 });
  }

  const url = new URL(request.url);
  const objectId = url.searchParams.get('object_id');
  if (!objectId) {
    return NextResponse.json({ error: 'object_id required' }, { status: 400 });
  }

  const upstream = await fetch(
    `${authConfig.internalApiBaseUrl}/v1/internal/audit?object_id=${encodeURIComponent(
      objectId,
    )}&page_size=100`,
    {
      headers: {
        Authorization: `Bearer ${authConfig.internalApiSecret()}`,
        'X-SBS-Role': persona.roles.join(','),
      },
      cache: 'no-store',
    },
  );
  if (!upstream.ok) {
    return NextResponse.json(
      { error: `upstream ${upstream.status}` },
      { status: upstream.status },
    );
  }
  const json = (await upstream.json()) as { items?: Array<Record<string, unknown>> };
  return NextResponse.json({ events: json.items ?? [] });
}
