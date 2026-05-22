// AnomalyCard — the highest-leverage UI element on the cockpit.
// Tooltip carries the composite-signal math so the demo answers
// "show me the math" without a pause.

'use client';

import Link from 'next/link';
import { AlertTriangle, ChevronRight } from 'lucide-react';

import {
  Badge,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui';
import { cn } from '@/lib/cn';
import type { AnomalyCardData, Severity } from '@/types/cockpit';

const SEVERITY_VARIANT: Record<Severity, 'low' | 'medium' | 'high' | 'critical'> = {
  low: 'low',
  medium: 'medium',
  high: 'high',
  critical: 'critical',
};

interface AnomalyCardProps {
  anomaly: AnomalyCardData;
  locale: string;
  labels: {
    threshold: string;
    composite: string;
    why_fired: string;
    channels: string;
    open_findings: string;
  };
}

function formatNumber(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function AnomalyCard({ anomaly, locale, labels }: AnomalyCardProps) {
  const findingsHref = `/findings?institution=${encodeURIComponent(
    anomaly.findings_filter.institution_id,
  )}&from=${encodeURIComponent(anomaly.findings_filter.from)}`;
  return (
    <TooltipProvider delayDuration={200}>
      <article
        className={cn(
          'flex flex-col gap-2 rounded-sbs border-l-4 bg-surface-elevated p-4 shadow-sm',
          'border-l-severity-' + anomaly.severity + '-border',
          'border border-border',
        )}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <AlertTriangle
              className="h-4 w-4 text-severity-high-fg"
              aria-hidden="true"
            />
            <h3 className="text-sm font-semibold text-fg">{anomaly.institution_name}</h3>
          </div>
          <Badge variant={SEVERITY_VARIANT[anomaly.severity]}>{anomaly.severity}</Badge>
        </div>

        <div className="flex items-center gap-3 text-sm">
          <div>
            <span className="text-fg-muted">{labels.composite}: </span>
            <span className="tabular font-medium text-fg">
              {formatNumber(anomaly.composite_score, locale)}
            </span>
          </div>
          <div className="text-fg-muted">·</div>
          <div>
            <span className="text-fg-muted">{labels.threshold}: </span>
            <span className="tabular text-fg">
              {formatNumber(anomaly.threshold, locale)}
            </span>
          </div>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label={labels.why_fired}
                className="ml-auto inline-flex h-6 items-center gap-1 rounded-sbs px-2 text-xs text-fg-link hover:bg-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2"
              >
                {labels.why_fired}
              </button>
            </TooltipTrigger>
            <TooltipContent>
              <p className="font-medium">{labels.channels}</p>
              <ul className="mt-1 space-y-0.5 text-xs">
                {anomaly.channel_contributions.map(c => (
                  <li key={c.channel} className="flex items-center justify-between gap-3 tabular">
                    <span className="text-fg-muted">{c.channel}</span>
                    <span className="text-fg">+{formatNumber(c.contribution, locale)}</span>
                  </li>
                ))}
              </ul>
            </TooltipContent>
          </Tooltip>
        </div>

        <Link
          href={findingsHref}
          className="inline-flex items-center gap-1 self-start text-xs text-fg-link underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2"
        >
          {labels.open_findings}
          <ChevronRight className="h-3 w-3" aria-hidden="true" />
        </Link>
      </article>
    </TooltipProvider>
  );
}
