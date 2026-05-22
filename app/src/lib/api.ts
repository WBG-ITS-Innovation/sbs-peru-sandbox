// Server-side helper for the Next.js → FastAPI server-to-server hop.
// Adds the shared-secret Authorization header, the X-SBS-Role header
// for role-scoping, and cache: 'no-store' so React Server Components
// don't accidentally cache mutable data across requests.

import 'server-only';

import { authConfig } from '@/auth/config';

interface CallOptions {
  /** Comma-joinable role identifiers forwarded as X-SBS-Role. */
  roles?: readonly string[];
}

function baseHeaders(opts?: CallOptions): Record<string, string> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${authConfig.internalApiSecret()}`,
    Accept: 'application/json',
  };
  if (opts?.roles && opts.roles.length > 0) {
    headers['X-SBS-Role'] = opts.roles.join(',');
  }
  return headers;
}

export async function internalGet<T>(path: string, opts?: CallOptions): Promise<T> {
  const response = await fetch(`${authConfig.internalApiBaseUrl}${path}`, {
    method: 'GET',
    headers: baseHeaders(opts),
    cache: 'no-store',
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`internalGet ${path} returned ${response.status}: ${text}`);
  }
  return (await response.json()) as T;
}

export async function internalPost<T>(
  path: string,
  body: unknown,
  opts?: CallOptions,
): Promise<T> {
  const response = await fetch(`${authConfig.internalApiBaseUrl}${path}`, {
    method: 'POST',
    headers: { ...baseHeaders(opts), 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    cache: 'no-store',
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`internalPost ${path} returned ${response.status}: ${text}`);
  }
  return (await response.json()) as T;
}
