import Link from 'next/link';
import { type ReactNode } from 'react';

import { cn } from '@/lib/cn';

// ADR 0041 D3 — the polish proof. Four required pieces (icon, title,
// body, primary action) + one optional (secondary link). The places
// the demo audience sees this component are the places polish either
// holds up or collapses; a generic "No results" is the failure mode
// the four-piece pattern guards against.
//
// Translation: title / body / labels come from the consuming page,
// which routes them through t(). The component shape is the contract;
// the strings are the consumer's responsibility.

export interface EmptyStateAction {
  label: string;
  href: string;
}

export interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  body: string;
  primaryAction: EmptyStateAction;
  secondaryLink?: EmptyStateAction;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  body,
  primaryAction,
  secondaryLink,
  className,
}: EmptyStateProps) {
  return (
    <div
      role="status"
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-sbs border border-dashed border-border bg-surface-subtle/40 p-10 text-center',
        className,
      )}
    >
      <div
        aria-hidden="true"
        className="flex h-12 w-12 items-center justify-center rounded-full bg-surface text-fg-muted"
      >
        {icon}
      </div>
      <h3 className="text-base font-semibold text-fg">{title}</h3>
      <p className="max-w-md text-sm text-fg-muted">{body}</p>
      <div className="mt-2 flex flex-col items-center gap-1.5">
        <Link
          href={primaryAction.href}
          className={cn(
            'inline-flex h-9 items-center justify-center rounded-sbs bg-brand-navy px-4 text-sm font-medium text-fg-inverted',
            'hover:bg-brand-navy/90',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2',
          )}
        >
          {primaryAction.label}
        </Link>
        {secondaryLink ? (
          <Link
            href={secondaryLink.href}
            className="text-xs text-fg-link underline-offset-4 hover:underline"
          >
            {secondaryLink.label}
          </Link>
        ) : null}
      </div>
    </div>
  );
}
