// BFF: GET /app/api/aggregates/feed → real findings from the DB.
// The RESHAPE cockpit/patterns route is not exposed on the configured
// backend build, so we fall back to /v1/internal/findings (confirmed
// working) — real complaint-level detections with live timestamps.

import { NextResponse } from 'next/server';

import { internalGet } from '@/lib/api';

export const dynamic = 'force-dynamic';

interface FindingRow {
  complaint_id: string;
  institution_id: string;
  institution_name: string;
  received_at: string;
  classification: string;
  confidence: number | null;
  severity: string;
  source: string;
  drafted_by_agent: boolean;
}

export async function GET() {
  try {
    const data = await internalGet<{ items: FindingRow[] }>(
      '/v1/internal/findings',
      { roles: ['sbs:conduct:head'] },
    );
    const items = data.items ?? [];
    return NextResponse.json(
      { items, generated_at: new Date().toISOString() },
      { headers: { 'Cache-Control': 'no-store' } },
    );
  } catch {
    return NextResponse.json(
      { items: [], generated_at: new Date().toISOString(), error: 'unavailable' },
      { status: 200 },
    );
  }
}
