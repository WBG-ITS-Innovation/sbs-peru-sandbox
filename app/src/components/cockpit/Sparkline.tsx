// SPDX-License-Identifier: Apache-2.0
import { cn } from '@/lib/cn';
import { sparklinePath } from '@/lib/sparkline';

interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  className?: string;
  ariaLabel: string;
}

export function Sparkline({
  values,
  width = 80,
  height = 24,
  className,
  ariaLabel,
}: SparklineProps) {
  const { d, width: w, height: h } = sparklinePath(values, { width, height });
  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={`0 0 ${w} ${h}`}
      width={w}
      height={h}
      className={cn('overflow-visible', className)}
    >
      <path
        d={d}
        stroke="currentColor"
        strokeWidth={1.5}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
