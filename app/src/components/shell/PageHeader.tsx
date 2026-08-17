// SPDX-License-Identifier: Apache-2.0
// PageHeader — the serif title row that lives directly under the
// navy TopBar inside the supervisor route group. The visual language
// matches the Claude Design artifact: a mono breadcrumb in caps, a
// Source-Serif title, a small institutional sub-line on the left, and
// an optional right cluster (refresh button, pilot badge, etc).
//
// This is a presentational component — no fetching, no state. Each
// page composes the right side as it sees fit.

import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

interface PageHeaderProps {
  breadcrumb?: string[];
  title: string;
  subtitle?: string;
  meta?: string;
  right?: ReactNode;
  className?: string;
}

export function PageHeader({
  breadcrumb,
  title,
  subtitle,
  meta,
  right,
  className,
}: PageHeaderProps) {
  return (
    <header
      className={cn(
        'flex flex-wrap items-end justify-between gap-3 border-b border-border bg-surface px-6 py-4',
        className,
      )}
    >
      <div className="min-w-0">
        {breadcrumb && breadcrumb.length > 0 ? (
          <p className="mb-1 flex flex-wrap items-center gap-1.5 font-mono text-2xs uppercase tracking-wider text-fg-muted">
            {breadcrumb.map((crumb, i) => (
              <span key={`${i}-${crumb}`} className="flex items-center gap-1.5">
                {i > 0 ? (
                  <span aria-hidden="true" className="text-fg-subtle">
                    ·
                  </span>
                ) : null}
                <span
                  className={
                    i === breadcrumb.length - 1 ? 'text-fg' : 'text-fg-muted'
                  }
                >
                  {crumb}
                </span>
              </span>
            ))}
          </p>
        ) : null}
        <h1 className="font-serif text-2xl font-semibold leading-tight tracking-tight text-fg">
          {title}
        </h1>
        {subtitle ? (
          <p className="mt-1 max-w-3xl text-sm text-fg-muted">{subtitle}</p>
        ) : null}
      </div>
      <div className="flex flex-shrink-0 items-center gap-3">
        {meta ? (
          <span className="font-mono text-2xs uppercase tracking-wider text-fg-muted">
            {meta}
          </span>
        ) : null}
        {right}
      </div>
    </header>
  );
}
