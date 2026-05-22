// KpiStrip — KPIs across the top of the cockpit, each with a small
// sparkline so the value is contextualised, not isolated.

import { Card, CardBody } from '@/components/ui';
import { cn } from '@/lib/cn';
import type { KpiData } from '@/types/cockpit';

import { Sparkline } from './Sparkline';

interface KpiStripProps {
  kpis: KpiData;
  locale: string;
  labels: {
    complaints_24h: string;
    anomalies_active: string;
    top_institutions: string;
  };
}

function fmtNum(n: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(n);
}

export function KpiStrip({ kpis, locale, labels }: KpiStripProps) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      <Card>
        <CardBody className="flex items-end justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-fg-muted">
              {labels.complaints_24h}
            </p>
            <p className="tabular text-3xl font-semibold text-fg">
              {fmtNum(kpis.complaints_24h, locale)}
            </p>
          </div>
          <Sparkline
            values={kpis.complaints_24h_sparkline}
            className="text-brand-cyan"
            ariaLabel={labels.complaints_24h}
          />
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          <p className="text-xs uppercase tracking-wider text-fg-muted">
            {labels.anomalies_active}
          </p>
          <p
            className={cn(
              'tabular text-3xl font-semibold',
              kpis.anomalies_active > 0 ? 'text-severity-high-fg' : 'text-fg',
            )}
          >
            {fmtNum(kpis.anomalies_active, locale)}
          </p>
        </CardBody>
      </Card>

      <Card>
        <CardBody>
          <p className="text-xs uppercase tracking-wider text-fg-muted">
            {labels.top_institutions}
          </p>
          <ul className="mt-1 space-y-1 text-sm">
            {kpis.top_institutions.map(inst => (
              <li
                key={inst.institution_id}
                className="flex items-baseline justify-between gap-2"
              >
                <span className="truncate text-fg">{inst.institution_name}</span>
                <span className="tabular text-fg-muted">
                  {fmtNum(inst.count_24h, locale)}
                </span>
              </li>
            ))}
            {kpis.top_institutions.length === 0 ? (
              <li className="text-xs text-fg-muted">—</li>
            ) : null}
          </ul>
        </CardBody>
      </Card>
    </div>
  );
}
