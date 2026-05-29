// BFF: GET /app/api/sandbox/tier2/status?batch_id=...&profile=... → poll the
// REAL Tier-2 status endpoint (GET /v1/batches/{id}). Returns the real
// lifecycle state + row counts (submitted / accepted / rejected).

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';
import { runSandbox } from '@/lib/sandbox-runner';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const PROFILES = new Set(['banco-tier1', 'coopac-tier2']);
const BATCH_ID = /^batch_[A-Za-z0-9]{16,32}$/;

export async function GET(request: Request) {
  if (!getSession(cookies().get(SESSION_COOKIE)?.value)) {
    return NextResponse.json({ error: 'unauthenticated' }, { status: 401 });
  }
  const url = new URL(request.url);
  const batchId = url.searchParams.get('batch_id') ?? '';
  const profile = PROFILES.has(url.searchParams.get('profile') ?? '') ? url.searchParams.get('profile')! : 'coopac-tier2';
  if (!BATCH_ID.test(batchId)) {
    return NextResponse.json({ error: 'invalid batch_id' }, { status: 400 });
  }
  try {
    const data = await runSandbox(['--mode', 'tier2-status', '--profile', profile, '--batch-id', batchId]);
    return NextResponse.json(data, { headers: { 'Cache-Control': 'no-store' } });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 502 });
  }
}
