// SPDX-License-Identifier: Apache-2.0
// Connection-state indicator — ADR 0040 §D5. The audience seeing the
// dot go amber while reconnecting is reassuring; the audience seeing
// a frozen UI is not. Always visible on every screen that consumes
// SSE — the cockpit places it in the page header for WS3.

'use client';

import { cn } from '@/lib/cn';
import type { ConnectionState } from '@/types/cockpit';

interface ConnectionStateDotProps {
  state: ConnectionState;
  label?: { connecting: string; connected: string; disconnected: string };
  className?: string;
}

export function ConnectionStateDot({
  state,
  label,
  className,
}: ConnectionStateDotProps) {
  const labels = label ?? {
    connecting: 'Connecting…',
    connected: 'Live',
    disconnected: 'Reconnecting…',
  };
  const labelText = labels[state];

  const colorClass =
    state === 'connected'
      ? 'bg-severity-low-fg'
      : state === 'connecting'
        ? 'bg-severity-medium-fg animate-pulse'
        : 'bg-severity-high-fg animate-pulse';

  return (
    <span
      className={cn('inline-flex items-center gap-1.5 text-xs text-fg-muted', className)}
      aria-live="polite"
    >
      <span
        aria-hidden="true"
        className={cn('inline-block h-2 w-2 rounded-full', colorClass)}
      />
      <span>{labelText}</span>
    </span>
  );
}
