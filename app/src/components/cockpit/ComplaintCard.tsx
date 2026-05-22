// ComplaintCard — used identically on both the Tier 1 and Tier 2
// panels. The visual sameness is the proportionality argument made
// visible (per the WS3 directive): both tiers produce the same
// Annex 1-A record; both render the same card.

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
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-2xs text-fg-muted">{complaint.complaint_id}</span>
        <Badge variant={SEVERITY_VARIANT[complaint.severity] ?? 'medium'}>
          {complaint.severity}
        </Badge>
      </div>
      <p className="mt-1.5 line-clamp-2 text-sm text-fg">{complaint.description_preview}</p>
      <div className="mt-2 flex items-center justify-between gap-2 text-2xs text-fg-muted">
        <span>{complaint.motivo_code} · {complaint.product_category}</span>
        <time dateTime={complaint.received_at} className="tabular">{timeLabel}</time>
      </div>
    </article>
  );
}
