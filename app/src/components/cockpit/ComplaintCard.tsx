// ComplaintCard — used identically on both the Tier 1 and Tier 2
// panels. The visual sameness is the proportionality argument made
// visible (per the WS3 directive): both tiers produce the same
// Annex 1-A record; both render the same card. Layout matches the
// Claude Design artifact: ID in font-mono brand-navy, severity pill,
// timestamp on the right, motivo / product / channel as a mono foot
// row with subtle separators.
//
// P11 demo-ui-polish overlay: when ``flag_unknown_taxonomy`` is true,
// the card grows a yellow left border (3px brand-gold), the ID gets
// an "Unknown term" pill next to it, and the pill carries a native
// tooltip listing up to three unknown surface forms (with "…" suffix
// when there are more).

import { Badge } from '@/components/ui';
import { t, type Locale } from '@/i18n';
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
  unknownPillLabel?: string;
}

function unknownTooltip(complaint: ComplaintCardData): string {
  const terms = complaint.unknown_terms ?? [];
  if (terms.length === 0) {
    return '';
  }
  const lines = terms.map(
    term => `${term.field_path}: "${term.original_value}"`,
  );
  const total = complaint.unknown_terms_total ?? terms.length;
  if (total > terms.length) {
    lines.push('…');
  }
  return lines.join('\n');
}

export function ComplaintCard({
  complaint,
  locale,
  className,
  unknownPillLabel,
}: ComplaintCardProps) {
  const i18nLocale = (locale === 'en-US' ? 'en-US' : 'es-PE') as Locale;
  const motivoLabel = t(i18nLocale, 'cockpit.complaint_card.motivo');
  const productoLabel = t(i18nLocale, 'cockpit.complaint_card.producto');
  const receivedAt = new Date(complaint.received_at);
  const timeLabel = new Intl.DateTimeFormat(locale, {
    timeZone: 'America/Lima',
    hour: '2-digit',
    minute: '2-digit',
    day: '2-digit',
    month: 'short',
  }).format(receivedAt);
  const flagged = complaint.flag_unknown_taxonomy === true;
  const pillTitle = flagged ? unknownTooltip(complaint) : '';

  return (
    <article
      className={cn(
        'rounded-sbs border border-border-subtle bg-surface p-3 transition-colors hover:border-border',
        flagged && 'border-l-[3px] border-l-brand-gold',
        className,
      )}
      data-flag-unknown-taxonomy={flagged ? 'true' : undefined}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs font-semibold tabular text-brand-navy">
          {complaint.complaint_id}
        </span>
        {flagged && unknownPillLabel ? (
          <Badge variant="warning" title={pillTitle}>
            {unknownPillLabel}
          </Badge>
        ) : null}
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
        <span className="text-fg-subtle">{motivoLabel}</span>{' '}
        <span className="text-fg">{complaint.motivo_code}</span>
        <span className="mx-1.5 text-border-strong">·</span>
        <span className="text-fg-subtle">{productoLabel}</span>{' '}
        <span className="text-fg">{complaint.product_category}</span>
      </p>
    </article>
  );
}
