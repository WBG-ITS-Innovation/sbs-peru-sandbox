// SPDX-License-Identifier: Apache-2.0
// BFF: POST /app/api/sandbox/tier2/submit → build a real Anexo-1A CSV of N
// rows + manifest and submit the multipart upload through the REAL Tier-2
// endpoint (POST /v1/batches, OAuth batch:upload + multipart HMAC + XFCC).
// Returns the real 202 receipt (batch_id, status, row_count_submitted).

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';
import { runSandbox } from '@/lib/sandbox-runner';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const PROFILES = new Set(['banco-tier1', 'coopac-tier2']);

export async function POST(request: Request) {
  if (!getSession(cookies().get(SESSION_COOKIE)?.value)) {
    return NextResponse.json({ error: 'unauthenticated' }, { status: 401 });
  }
  let body: { profile?: string; rows?: number } = {};
  try {
    body = (await request.json()) as typeof body;
  } catch {
    /* defaults */
  }
  const profile = PROFILES.has(body.profile ?? '') ? body.profile! : 'coopac-tier2';
  const rows = Math.max(1, Math.min(Number(body.rows) || 20, 200));
  try {
    const data = await runSandbox(['--mode', 'tier2', '--profile', profile, '--rows', String(rows)]);
    return NextResponse.json(data, { headers: { 'Cache-Control': 'no-store' } });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 502 });
  }
}
