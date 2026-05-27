// POST /app/api/journey/submit — Stage 3 of the demo-journey overlay.
//
// Receives the form-derived granular complaint body from the browser,
// spawns scripts/journey_submit.py which runs the real institutional
// auth chain (mTLS-proxy via dev XFCC + OAuth + HMAC + Idempotency-Key)
// against POST /v1/sandbox/complaints/granular, and returns the
// structured trace + receipt.
//
// Auth gates: valid supervisor session + CSRF header. The shared
// internal secret is not used here — this path makes a real signed
// institutional call, not an internal one.

import { spawn } from 'node:child_process';
import path from 'node:path';

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { SESSION_COOKIE } from '@/auth/cookies';
import { checkCsrf } from '@/auth/csrf';
import { activePersona, getSession } from '@/auth/session';

// Force Node runtime; child_process is unavailable on edge.
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const REPO_ROOT = path.resolve(process.cwd(), '..');
const VENV_PY = path.join(REPO_ROOT, '.venv', 'bin', 'python');
const SCRIPT = path.join(REPO_ROOT, 'scripts', 'journey_submit.py');
const API_BASE = process.env.SBS_SANDBOX_API_BASE ?? 'http://localhost:8000/v1';

interface SubmitResult {
  ok: boolean;
  error?: string;
  trace?: Record<string, unknown>;
  receipt?: unknown;
}

function runJourneySubmit(payload: unknown): Promise<SubmitResult> {
  return new Promise((resolve) => {
    const child = spawn(VENV_PY, [SCRIPT, '--api-base', API_BASE], {
      env: { ...process.env, PYTHONPATH: path.join(REPO_ROOT, 'api') },
      cwd: REPO_ROOT,
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk: Buffer) => {
      stdout += chunk.toString('utf-8');
    });
    child.stderr.on('data', (chunk: Buffer) => {
      stderr += chunk.toString('utf-8');
    });
    const timer = setTimeout(() => {
      child.kill('SIGTERM');
      resolve({ ok: false, error: 'journey_submit timed out after 15s' });
    }, 15_000);
    child.on('close', () => {
      clearTimeout(timer);
      const last = stdout.trim().split('\n').filter(Boolean).pop() ?? '';
      try {
        resolve(JSON.parse(last) as SubmitResult);
      } catch {
        resolve({
          ok: false,
          error: `journey_submit produced no JSON. stderr=${stderr.slice(0, 400)}`,
        });
      }
    });
    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}

export async function POST(request: Request) {
  if (!checkCsrf(request)) {
    return NextResponse.json({ ok: false, error: 'csrf' }, { status: 403 });
  }
  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    return NextResponse.json({ ok: false, error: 'unauthenticated' }, { status: 401 });
  }
  const persona = activePersona(session);
  if (persona.roles.length === 0) {
    return NextResponse.json({ ok: false, error: 'no_role' }, { status: 403 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false, error: 'invalid_json' }, { status: 400 });
  }

  const result = await runJourneySubmit(body);
  return NextResponse.json(result, { status: 200 });
}
