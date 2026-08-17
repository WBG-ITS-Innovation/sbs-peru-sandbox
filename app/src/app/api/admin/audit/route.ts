// SPDX-License-Identifier: Apache-2.0
// BFF: GET /app/api/admin/audit → recent rows from the REAL audit log
// (/v1/internal/audit). Read-only; used by the IT/sandbox-admin view.

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { SESSION_COOKIE } from '@/auth/cookies';
import { activePersona, getSession } from '@/auth/session';
import { internalGet } from '@/lib/api';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function GET(request: Request) {
  const session = getSession((await cookies()).get(SESSION_COOKIE)?.value);
  if (!session) {
    return NextResponse.json({ error: 'unauthenticated' }, { status: 401 });
  }
  const persona = activePersona(session);
  const url = new URL(request.url);
  const pageSize = Math.max(1, Math.min(Number(url.searchParams.get('page_size')) || 20, 50));
  try {
    const data = await internalGet<Record<string, unknown>>(
      `/v1/internal/audit?page_size=${pageSize}&page=1`,
      { roles: persona.roles },
    );
    return NextResponse.json(data, { headers: { 'Cache-Control': 'no-store' } });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 502 });
  }
}
