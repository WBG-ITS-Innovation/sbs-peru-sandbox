// SPDX-License-Identifier: Apache-2.0
import 'server-only';

import { spawn } from 'node:child_process';
import path from 'node:path';

import { pythonBin } from '@/lib/python';

// Spawns scripts/sandbox_send.py (the REAL signed sender) and returns its
// JSON output. Next dev/build runs with cwd = app/, so the repo root is the
// parent. Secrets (HMAC, client_secret) live in the script/seed and never
// reach the browser — the BFF only relays the real API response.
const REPO_ROOT = path.resolve(process.cwd(), '..');
const SCRIPT = path.join(REPO_ROOT, 'scripts', 'sandbox_send.py');

export interface RunOpts {
  stdin?: string;
  timeoutMs?: number;
}

export async function runSandbox<T = unknown>(args: string[], opts: RunOpts = {}): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const child = spawn(pythonBin(), [SCRIPT, ...args], { cwd: REPO_ROOT });
    let out = '';
    let err = '';
    const timer = setTimeout(() => {
      child.kill('SIGKILL');
      reject(new Error('sandbox_send timed out'));
    }, opts.timeoutMs ?? 90_000);

    child.stdout.on('data', (d) => (out += d.toString()));
    child.stderr.on('data', (d) => (err += d.toString()));
    child.on('error', (e) => {
      clearTimeout(timer);
      reject(e);
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      const trimmed = out.trim();
      if (trimmed) {
        try {
          resolve(JSON.parse(trimmed) as T);
          return;
        } catch {
          /* fall through to error */
        }
      }
      reject(new Error(`sandbox_send exit ${code}: ${err.slice(0, 600) || 'no output'}`));
    });

    if (opts.stdin != null) {
      child.stdin.write(opts.stdin);
    }
    child.stdin.end();
  });
}
