// SPDX-License-Identifier: Apache-2.0
// BFF: GET /app/api/aggregates/trend → real motivo distribution + monthly
// volume (with social-signal overlay) for the charts tab. Proxies the
// server-to-server internal endpoint. Degrades to empty arrays on error.

import { NextResponse } from 'next/server';

import { internalGet } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const data = await internalGet<Record<string, unknown>>(
      '/v1/internal/aggregates/trend',
      { roles: ['sbs:conduct:head'] },
    );
    return NextResponse.json(data, { headers: { 'Cache-Control': 'no-store' } });
  } catch {
    return NextResponse.json(
      { generated_at: new Date().toISOString(), by_motivo: [], by_month: [], error: 'unavailable' },
      { status: 200 },
    );
  }
}
