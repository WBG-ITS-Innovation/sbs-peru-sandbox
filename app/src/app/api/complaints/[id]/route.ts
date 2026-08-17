// SPDX-License-Identifier: Apache-2.0
// BFF: GET /app/api/complaints/{id} → full canonical complaint record for the
// processing detail's "Detalle del reclamo" panel. Proxies the internal
// endpoint with the shared secret + the caller's roles.

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { SESSION_COOKIE } from '@/auth/cookies';
import { activePersona, getSession } from '@/auth/session';
import { internalGet } from '@/lib/api';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function GET(_request: Request, { params }: { params: { id: string } }) {
  const session = getSession(cookies().get(SESSION_COOKIE)?.value);
  if (!session) {
    return NextResponse.json({ error: 'unauthenticated' }, { status: 401 });
  }
  const persona = activePersona(session);
  try {
    const data = await internalGet<Record<string, unknown>>(
      `/v1/internal/complaints/${encodeURIComponent(params.id)}`,
      { roles: persona.roles },
    );
    return NextResponse.json(data, { headers: { 'Cache-Control': 'no-store' } });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 502 });
  }
}
