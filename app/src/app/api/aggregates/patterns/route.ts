// BFF: GET /app/api/aggregates/patterns?scope=entity|group|all
// Proxies the server-to-server internal endpoint (which needs the shared
// secret the browser must never hold) → GET /v1/internal/aggregates/patterns.
// Real SQL-computed rows; degrades to {rows:[]} on upstream error.

import { NextResponse } from 'next/server';

import { internalGet } from '@/lib/api';

export const dynamic = 'force-dynamic';

const SCOPES = new Set(['entity', 'group', 'all']);

export async function GET(request: Request) {
  const requested = new URL(request.url).searchParams.get('scope') ?? 'entity';
  const scope = SCOPES.has(requested) ? requested : 'entity';
  try {
    const data = await internalGet<Record<string, unknown>>(
      `/v1/internal/aggregates/patterns?scope=${encodeURIComponent(scope)}`,
      { roles: ['sbs:conduct:head'] },
    );
    return NextResponse.json(data, { headers: { 'Cache-Control': 'no-store' } });
  } catch {
    return NextResponse.json(
      {
        scope,
        generated_at: new Date().toISOString(),
        total_in_scope: 0,
        rows: [],
        error: 'unavailable',
      },
      { status: 200 },
    );
  }
}
