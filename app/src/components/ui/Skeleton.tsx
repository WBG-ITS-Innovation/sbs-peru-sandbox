// SPDX-License-Identifier: Apache-2.0
import { type HTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

// Skeleton — used for every async region while data is loading. The
// animation is a subtle pulse, not a shimmer; "deliberate, not retro".
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn('animate-pulse rounded-sbs bg-surface-subtle', className)}
      {...props}
    />
  );
}
