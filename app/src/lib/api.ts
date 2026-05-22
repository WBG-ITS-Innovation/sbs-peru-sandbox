// Server-side helper for the Next.js → FastAPI server-to-server hop.
// Adds the shared-secret Authorization header and the cache: 'no-store'
// hint so React Server Components don't accidentally cache mutable
// data across requests.

import 'server-only';

import { authConfig } from '@/auth/config';

export async function internalGet<T>(path: string): Promise<T> {
  const response = await fetch(`${authConfig.internalApiBaseUrl}${path}`, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${authConfig.internalApiSecret()}`,
      Accept: 'application/json',
    },
    cache: 'no-store',
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`internalGet ${path} returned ${response.status}: ${text}`);
  }
  return (await response.json()) as T;
}
