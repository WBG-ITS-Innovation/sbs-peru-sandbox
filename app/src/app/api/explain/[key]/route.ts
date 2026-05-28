// BFF: GET /app/api/explain/{key} → FastAPI /v1/internal/explain/{key}.
// Lets the client-side Explanation component consume the RESHAPE-5
// explanation registry by key without exposing the shared secret. The
// active persona (cookie) supplies the X-SBS-Role scope.

import { NextResponse } from 'next/server';

import { activePersona, personaGet } from '@/auth/persona-server';
import type { ExplainEntry } from '@/types/persona-dashboards';

export const dynamic = 'force-dynamic';

export async function GET(
  _request: Request,
  { params }: { params: { key: string } },
) {
  const persona = activePersona();
  if (!persona) {
    return NextResponse.json({ error: 'no_active_persona' }, { status: 401 });
  }
  try {
    const data = await personaGet<ExplainEntry>(
      persona,
      `/v1/internal/explain/${encodeURIComponent(params.key)}`,
    );
    return NextResponse.json(data, {
      headers: { 'Cache-Control': 'no-store' },
    });
  } catch {
    return NextResponse.json({ error: 'not_found' }, { status: 404 });
  }
}
