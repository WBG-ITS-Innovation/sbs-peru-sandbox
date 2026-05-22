// KPI strip on the approvals queue header.

import { Card, CardBody } from '@/components/ui';
import { cn } from '@/lib/cn';
import type { ApprovalKpis } from '@/types/approvals';

interface ApprovalKpisProps {
  kpis: ApprovalKpis;
  locale: string;
  labels: {
    pending: string;
    approved_today: string;
    rejected_today: string;
    median_ttd: string;
  };
}

function fmtSeconds(s: number | null, locale: string): string {
  if (s === null) return '—';
  if (s < 60) return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(s) + ' s';
  if (s < 3600) return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(s / 60) + ' min';
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(s / 3600) + ' h';
}

export function ApprovalKpisStrip({ kpis, locale, labels }: ApprovalKpisProps) {
  const nf = new Intl.NumberFormat(locale);
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <KpiCard
        label={labels.pending}
        value={nf.format(kpis.pending)}
        emphasis={kpis.pending > 0}
      />
      <KpiCard label={labels.approved_today} value={nf.format(kpis.approved_today)} />
      <KpiCard label={labels.rejected_today} value={nf.format(kpis.rejected_today)} />
      <KpiCard
        label={labels.median_ttd}
        value={fmtSeconds(kpis.median_time_to_decision_seconds, locale)}
      />
    </div>
  );
}

function KpiCard({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <Card>
      <CardBody>
        <p className="text-xs uppercase tracking-wider text-fg-muted">{label}</p>
        <p
          className={cn(
            'tabular text-2xl font-semibold',
            emphasis ? 'text-severity-high-fg' : 'text-fg',
          )}
        >
          {value}
        </p>
      </CardBody>
    </Card>
  );
}
