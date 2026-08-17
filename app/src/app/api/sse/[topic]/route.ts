// SPDX-License-Identifier: Apache-2.0
// GET /app/api/sse/[topic] — proxies the EventSource connection from
// the browser to FastAPI's /v1/internal/sse/{topic}. The shared
// secret never reaches the browser; the session cookie gates whether
// the user is allowed to open a stream.

import { cookies } from 'next/headers';

import { authConfig } from '@/auth/config';
import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';

export const dynamic = 'force-dynamic';

export async function GET(request: Request, props: { params: Promise<{ topic: string }> }) {
  const params = await props.params;
  const sessionId = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    return new Response(null, { status: 401 });
  }

  const personas = session.personas as Record<string, { roles?: readonly string[] }>;
  const activePersona = personas[session.activePersonaKey];
  const roles = activePersona?.roles ?? [];
  if (roles.length === 0) {
    return new Response(null, { status: 403 });
  }

  const lastEventId = request.headers.get('Last-Event-ID');

  const upstream = await fetch(
    `${authConfig.internalApiBaseUrl}/v1/internal/sse/${params.topic}`,
    {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${authConfig.internalApiSecret()}`,
        Accept: 'text/event-stream',
        'X-SBS-Role': roles.join(','),
        ...(lastEventId ? { 'Last-Event-ID': lastEventId } : {}),
      },
      // SSE is a long-lived stream — disable caching and let Next.js
      // pipe the body through.
      cache: 'no-store',
    },
  );

  if (!upstream.ok || !upstream.body) {
    return new Response(null, { status: upstream.status });
  }

  return new Response(upstream.body, {
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}
