// ComplaintCard — used identically on both the Tier 1 and Tier 2
// panels. The visual sameness is the proportionality argument made
// visible (per the WS3 directive): both tiers produce the same
// Annex 1-A record; both render the same card. Layout matches the
// Claude Design artifact: ID in font-mono brand-navy, severity pill,
// timestamp on the right, motivo / product / channel as a mono foot
// row with subtle separators.

import { Badge } from '@/components/ui';
import { cn } from '@/lib/cn';
import type { ComplaintCardData, Severity } from '@/types/cockpit';

const SEVERITY_VARIANT: Record<Severity, 'low' | 'medium' | 'high' | 'critical'> = {
  low: 'low',
  medium: 'medium',
  high: 'high',
  critical: 'critical',
};

interface ComplaintCardProps {
  complaint: ComplaintCardData;
  locale: string;
  className?: string;
}

export function ComplaintCard({ complaint, locale, className }: ComplaintCardProps) {
  const receivedAt = new Date(complaint.received_at);
  const timeLabel = new Intl.DateTimeFormat(locale, {
    timeZone: 'America/Lima',
    hour: '2-digit',
    minute: '2-digit',
    day: '2-digit',
    month: 'short',
  }).format(receivedAt);

  return (
    <article
      className={cn(
        'rounded-sbs border border-border-subtle bg-surface p-3 transition-colors hover:border-border',
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs font-semibold tabular text-brand-navy">
          {complaint.complaint_id}
        </span>
        <Badge variant={SEVERITY_VARIANT[complaint.severity] ?? 'medium'}>
          {complaint.severity.toUpperCase()}
        </Badge>
        <time
          dateTime={complaint.received_at}
          className="ml-auto font-mono text-2xs tabular text-fg-muted"
        >
          {timeLabel}
        </time>
      </div>
      <p className="mt-2 line-clamp-2 text-sm leading-snug text-fg">
        {complaint.description_preview}
      </p>
      <p className="mt-2 font-mono text-2xs uppercase tracking-wider text-fg-muted">
        <span className="text-fg-subtle">motivo</span>{' '}
        <span className="text-fg">{complaint.motivo_code}</span>
        <span className="mx-1.5 text-border-strong">·</span>
        <span className="text-fg-subtle">producto</span>{' '}
        <span className="text-fg">{complaint.product_category}</span>
      </p>
    </article>
  );
}
