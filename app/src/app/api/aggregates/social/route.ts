// BFF: GET /app/api/aggregates/social → real social-signal telemetry.
// Proxies GET /v1/internal/ops/social_health (OPS_READ → sbs:sbs_it role).
// The upstream is PII-suppressed by design: it returns aggregate
// fraud-indicator counts + per-source signal counts, NOT post text,
// topics, or institution names. So the social card surfaces indicador +
// menciones + fuentes (real), not topic/institution detail.
// available:false lets the client fall back to clearly-labelled sample.

import { NextResponse } from 'next/server';

import { internalGet } from '@/lib/api';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const data = await internalGet<Record<string, unknown>>(
      '/v1/internal/ops/social_health',
      { roles: ['sbs:sbs_it'] },
    );
    return NextResponse.json(
      { available: true, ...data },
      { headers: { 'Cache-Control': 'no-store' } },
    );
  } catch {
    return NextResponse.json({ available: false }, { status: 200 });
  }
}
