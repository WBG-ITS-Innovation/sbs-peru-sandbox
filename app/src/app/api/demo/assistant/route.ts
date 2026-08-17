// SPDX-License-Identifier: Apache-2.0
// POST /app/api/demo/assistant — proxy for the assistant chat box.
//
// Spawns scripts/assistant_query.py which calls Azure OpenAI with three
// database-backed tool functions. The script returns a single JSON
// line carrying the final answer + the tool-call trail.

import { spawn } from 'node:child_process';
import path from 'node:path';

import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

import { SESSION_COOKIE } from '@/auth/cookies';
import { checkCsrf } from '@/auth/csrf';
import { activePersona, getSession } from '@/auth/session';

import { pythonBin } from '@/lib/python';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

const REPO_ROOT = path.resolve(process.cwd(), '..');
const SCRIPT = path.join(REPO_ROOT, 'scripts', 'assistant_query.py');

interface AssistantResult {
  ok: boolean;
  answer?: string;
  error?: string;
  model?: string;
  tool_calls?: Array<{ name: string; args: Record<string, unknown>; result: unknown }>;
}

function runAssistant(payload: unknown): Promise<AssistantResult> {
  return new Promise((resolve) => {
    // Pass the AZURE_OPENAI_* vars from the dev server's env. In prod
    // these come from Helm; in dev `bash scripts/run-api.sh` already
    // loads .env and the Next dev server inherits it.
    const child = spawn(pythonBin(), [SCRIPT], { cwd: REPO_ROOT, env: process.env });
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
      resolve({ ok: false, error: 'assistant_query timed out after 35s' });
    }, 35_000);
    child.on('close', () => {
      clearTimeout(timer);
      const line = stdout.trim().split('\n').filter(Boolean).pop() || '';
      try {
        resolve(JSON.parse(line) as AssistantResult);
      } catch {
        resolve({
          ok: false,
          error: `assistant_query produced no JSON. stderr=${stderr.slice(0, 300)}`,
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
  const sessionId = (await cookies()).get(SESSION_COOKIE)?.value;
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
  const result = await runAssistant(body);
  return NextResponse.json(result, { status: 200 });
}
