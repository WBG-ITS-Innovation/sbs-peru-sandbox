// useSSE — client-side SSE consumer with snapshot + delta + reconnect.
//
// ADR 0040 §D5 contract:
// - Server emits one event:snapshot with id=0 on a fresh connect.
// - Subsequent event:* messages carry deltas.
// - On reconnect, the EventSource sends Last-Event-ID natively; the
//   server replays from the ring buffer.
// - If the server cannot replay (events aged out of the buffer), it
//   emits event:resync-required and the client refetches the snapshot.
//
// The hook exposes a stable `state` (which the consuming UI renders)
// and a `connectionState` ('connecting' | 'connected' | 'disconnected')
// that drives the ConnectionStateDot in the nav rail.

'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import type { ConnectionState } from '@/types/cockpit';

export interface SSEMessage<T = unknown> {
  event: string;
  data: T;
  lastEventId: string;
}

export interface UseSSEOptions<TState> {
  /** URL the EventSource opens — usually /api/sse/<topic>. */
  url: string;
  /** Initial state — typically the server-rendered snapshot. */
  initialState: TState;
  /** Reduce a delta into the running state. */
  reduce: (state: TState, message: SSEMessage<unknown>) => TState;
  /**
   * Called when the server emits event:resync-required; the consumer
   * should refetch its snapshot and pass the new state via setState().
   */
  onResyncRequired?: () => void;
  /** Optional — disable the connection (e.g., during SSR). */
  enabled?: boolean;
}

export interface UseSSEResult<TState> {
  state: TState;
  setState: (next: TState) => void;
  connectionState: ConnectionState;
  lastEventId: string | null;
}

const INITIAL_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30000;

export function useSSE<TState>({
  url,
  initialState,
  reduce,
  onResyncRequired,
  enabled = true,
}: UseSSEOptions<TState>): UseSSEResult<TState> {
  const [state, setStateRaw] = useState<TState>(initialState);
  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting');
  const [lastEventId, setLastEventId] = useState<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);
  const backoffRef = useRef<number>(INITIAL_BACKOFF_MS);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const setState = useCallback((next: TState) => setStateRaw(next), []);

  useEffect(() => {
    if (!enabled) {
      setConnectionState('disconnected');
      return;
    }

    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      setConnectionState('connecting');

      // The browser's EventSource API automatically sends Last-Event-ID
      // on reconnect from the previously-received id, so we don't need
      // to manage that header explicitly here. We just keep the URL
      // stable.
      const es = new EventSource(url, { withCredentials: true });
      sourceRef.current = es;

      es.onopen = () => {
        if (cancelled) return;
        setConnectionState('connected');
        backoffRef.current = INITIAL_BACKOFF_MS;
      };

      const handleMessage = (event: MessageEvent) => {
        if (cancelled) return;
        if (event.lastEventId) setLastEventId(event.lastEventId);
        const eventName = event.type === 'message' ? 'message' : event.type;

        if (eventName === 'resync-required') {
          onResyncRequired?.();
          return;
        }

        let data: unknown;
        try {
          data = event.data ? JSON.parse(event.data) : undefined;
        } catch {
          // Ignore malformed payloads — the server is the contract.
          return;
        }

        setStateRaw(prev =>
          reduce(prev, {
            event: eventName,
            data,
            lastEventId: event.lastEventId,
          }),
        );
      };

      // Register every event type we expect. The 'message' default
      // fires for any unnamed event; named events route through
      // addEventListener with the exact name.
      es.addEventListener('snapshot', handleMessage);
      es.addEventListener('complaint.received', handleMessage);
      es.addEventListener('anomaly.detected', handleMessage);
      es.addEventListener('signal.threshold.crossed', handleMessage);
      es.addEventListener('resync-required', handleMessage);
      es.onmessage = handleMessage;

      es.onerror = () => {
        if (cancelled) return;
        setConnectionState('disconnected');
        es.close();
        sourceRef.current = null;
        const delay = backoffRef.current;
        backoffRef.current = Math.min(delay * 2, MAX_BACKOFF_MS);
        reconnectTimer.current = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      sourceRef.current?.close();
      sourceRef.current = null;
    };
  }, [url, enabled, reduce, onResyncRequired]);

  return { state, setState, connectionState, lastEventId };
}
