// Lightweight connection-state probe — opens an EventSource purely to
// track whether the SSE stream is reachable, ignoring the payload.
// Used by the AppShell's ConnectionStateDot in the top bar so the dot
// can render correctly on every screen without each screen having to
// own a connection. The full data-carrying connection still lives in
// the consuming page (cockpit's useSSE, etc.).
//
// Two EventSources per topic per browser is wasteful in the long run;
// WS7 collapses this into a single context-provided connection. For
// WS4 the duplication is acceptable.

'use client';

import { useEffect, useState } from 'react';

import type { ConnectionState } from '@/types/cockpit';

export function useConnectionState(topic: string): ConnectionState {
  const [state, setState] = useState<ConnectionState>('connecting');

  useEffect(() => {
    let cancelled = false;
    let es: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let backoff = 1000;

    const connect = () => {
      if (cancelled) return;
      setState('connecting');
      es = new EventSource(`/app/api/sse/${topic}`, { withCredentials: true });
      es.onopen = () => {
        if (cancelled) return;
        setState('connected');
        backoff = 1000;
      };
      es.onerror = () => {
        if (cancelled) return;
        setState('disconnected');
        es?.close();
        es = null;
        retryTimer = setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, 30000);
      };
      // Discard payloads — this hook only cares about connectivity.
      es.onmessage = () => {};
    };

    connect();

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      es?.close();
    };
  }, [topic]);

  return state;
}
