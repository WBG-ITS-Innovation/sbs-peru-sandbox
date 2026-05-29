// BFF: POST /app/api/sandbox/tier1/pool → generate N candidate Tier-1
// complaint payloads (the synthetic pool the bank draws from). No send;
// the UI lists these so the operator can pick one to push. Real generator
// (scripts/sandbox_send.py --mode pool).

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
  let body: { profile?: string; count?: number } = {};
  try {
    body = (await request.json()) as typeof body;
  } catch {
    /* defaults */
  }
  const profile = PROFILES.has(body.profile ?? '') ? body.profile! : 'banco-tier1';
  const count = Math.max(1, Math.min(Number(body.count) || 12, 24));
  try {
    const data = await runSandbox(['--mode', 'pool', '--profile', profile, '--count', String(count)]);
    return NextResponse.json(data, { headers: { 'Cache-Control': 'no-store' } });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 502 });
  }
}
