// GET /app/api/journey/insights — richer cockpit aggregates.
// Backs the new /app/cockpit insights board + granular explorer.

import { spawn } from 'node:child_process';
import path from 'node:path';

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { SESSION_COOKIE } from '@/auth/cookies';
import { activePersona, getSession } from '@/auth/session';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const REPO_ROOT = path.resolve(process.cwd(), '..');
const VENV_PY = path.join(REPO_ROOT, '.venv', 'bin', 'python');
const SCRIPT = path.join(REPO_ROOT, 'scripts', 'cockpit_insights.py');

function run(): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const child = spawn(VENV_PY, [SCRIPT], { cwd: REPO_ROOT });
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
      reject(new Error('cockpit_insights timed out'));
    }, 10_000);
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

export async function GET() {
  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    return NextResponse.json({ error: 'unauthenticated' }, { status: 401 });
  }
  const persona = activePersona(session);
  if (persona.roles.length === 0) {
    return NextResponse.json({ error: 'no_role' }, { status: 403 });
  }
  try {
    return NextResponse.json(await run());
  } catch (exc) {
    return NextResponse.json({ error: String(exc) }, { status: 500 });
  }
}
