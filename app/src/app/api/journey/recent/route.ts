// SPDX-License-Identifier: Apache-2.0
// GET /app/api/journey/recent?limit=20 — recent complaints + agent state.
//
// Shells out to scripts/recent_complaints.py so the Postgres driver
// stays out of the Next runtime. Used by both /app/ingestion (live
// ticker) and /app/processing (per-complaint drill-in).

import { spawn } from 'node:child_process';
import path from 'node:path';

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { SESSION_COOKIE } from '@/auth/cookies';
import { activePersona, getSession } from '@/auth/session';

import { pythonBin } from '@/lib/python';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const REPO_ROOT = path.resolve(process.cwd(), '..');
const SCRIPT = path.join(REPO_ROOT, 'scripts', 'recent_complaints.py');

function run(limit: number): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonBin(), [SCRIPT, '--limit', String(limit)], {
      cwd: REPO_ROOT,
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (c: Buffer) => {
      stdout += c.toString('utf-8');
    });
    child.stderr.on('data', (c: Buffer) => {
      stderr += c.toString('utf-8');
    });
    const timer = setTimeout(() => {
      child.kill('SIGTERM');
      reject(new Error('recent_complaints timed out'));
    }, 8000);
    child.on('close', () => {
      clearTimeout(timer);
      const line = stdout.trim().split('\n').filter(Boolean).pop() || '';
      try {
        resolve(JSON.parse(line));
      } catch {
        reject(new Error(`bad json. stderr=${stderr.slice(0, 200)}`));
      }
    });
  });
}

export async function GET(request: Request) {
  const sessionId = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    return NextResponse.json({ error: 'unauthenticated' }, { status: 401 });
  }
  const persona = activePersona(session);
  if (persona.roles.length === 0) {
    return NextResponse.json({ error: 'no_role' }, { status: 403 });
  }
  const url = new URL(request.url);
  const limit = Math.min(
    100,
    Math.max(1, Number.parseInt(url.searchParams.get('limit') || '20', 10) || 20),
  );
  try {
    const data = await run(limit);
    return NextResponse.json({ items: data });
  } catch (exc) {
    return NextResponse.json({ error: String(exc) }, { status: 500 });
  }
}
