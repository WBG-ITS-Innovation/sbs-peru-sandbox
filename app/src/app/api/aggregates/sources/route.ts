// SPDX-License-Identifier: Apache-2.0
// BFF: GET /app/api/aggregates/sources → real cross-source aggregates
// (social_signals + indecopi_cases, PII-safe) for the red-flags view.
// Proxies the internal endpoint; degrades to empty arrays on error.

import { NextResponse } from 'next/server';

import { internalGet } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const data = await internalGet<Record<string, unknown>>(
      '/v1/internal/aggregates/sources',
      { roles: ['sbs:conduct:head'] },
    );
    return NextResponse.json(data, { headers: { 'Cache-Control': 'no-store' } });
  } catch {
    return NextResponse.json(
      {
        generated_at: new Date().toISOString(),
        social_by_indicator: [],
        social_institution_codes: [],
        social_total: 0,
        indecopi: [],
        indecopi_institution_ids: [],
        error: 'unavailable',
      },
      { status: 200 },
    );
  }
}
