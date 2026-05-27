// TaxonomyStatsTile — small stat tile showing today's taxonomy
// normalization activity. Reads from
// GET /v1/internal/cockpit/taxonomy-stats via the Next.js bridge.
// Rendered alongside the live ingestion panel on the cockpit page.

import { Card, CardBody } from '@/components/ui';
import { cn } from '@/lib/cn';

interface TaxonomyStatsTileProps {
  stats: {
    normalizations_today: number;
    institutions_affected: number;
    as_of: string;
  };
  labels: {
    title: string;
    summary: (n: number, m: number) => string;
    as_of_prefix: string;
  };
  locale: string;
  className?: string;
}

function fmtNum(n: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(n);
}

export function TaxonomyStatsTile({
  stats,
  labels,
  locale,
  className,
}: TaxonomyStatsTileProps) {
  const time = new Intl.DateTimeFormat(locale, {
    timeZone: 'America/Lima',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(stats.as_of));
  return (
    <Card className={cn('border-border', className)}>
      <CardBody className="px-4 py-3">
        <p className="font-mono text-2xs font-medium uppercase tracking-wider text-fg-muted">
          {labels.title}
        </p>
        <p className="mt-1 font-mono text-3xl font-semibold leading-none tabular text-brand-navy">
          {fmtNum(stats.normalizations_today, locale)}
        </p>
        <p className="mt-1 text-xs text-fg-muted">
          {labels.summary(stats.normalizations_today, stats.institutions_affected)}
        </p>
        <p className="mt-2 font-mono text-2xs uppercase tracking-wider text-fg-subtle">
          {labels.as_of_prefix} {time}
        </p>
      </CardBody>
    </Card>
  );
}
