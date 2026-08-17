// SPDX-License-Identifier: Apache-2.0
// BFF: POST /app/api/sandbox/tier1/send → send 1..N complaints through the
// REAL Tier-1 endpoint (POST /v1/sandbox/complaints/granular, OAuth+HMAC+XFCC).
// Body: { profile, count }  → send `count` freshly-generated complaints (burst).
//       { profile, payload } → send one selected complaint from the pool.
// Returns the real per-send receipts (status, complaint_id, DQ verdict).

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
  let body: { profile?: string; count?: number; payload?: Record<string, unknown> } = {};
  try {
    body = (await request.json()) as typeof body;
  } catch {
    /* defaults */
  }
  const profile = PROFILES.has(body.profile ?? '') ? body.profile! : 'banco-tier1';
  try {
    if (body.payload && typeof body.payload === 'object') {
      const data = await runSandbox(
        ['--mode', 'tier1', '--profile', profile, '--payload-file', '-'],
        { stdin: JSON.stringify(body.payload) },
      );
      return NextResponse.json(data, { headers: { 'Cache-Control': 'no-store' } });
    }
    const count = Math.max(1, Math.min(Number(body.count) || 1, 50));
    const data = await runSandbox(['--mode', 'tier1', '--profile', profile, '--count', String(count)]);
    return NextResponse.json(data, { headers: { 'Cache-Control': 'no-store' } });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 502 });
  }
}
