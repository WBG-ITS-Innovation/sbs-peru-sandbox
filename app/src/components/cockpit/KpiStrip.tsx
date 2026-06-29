// SPDX-License-Identifier: Apache-2.0
// KpiStrip — three KPI tiles across the top of the cockpit. Visual
// language from the Claude Design artifact: tight padding, mono
// numerics with tabular figures, all-caps labels in mono micro-caps,
// the second tile uses brand-gold for the active-anomalies number to
// make a non-zero state pop. Real data — these read state.kpis from
// the live snapshot/SSE merge.

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
      <Card className="border-border">
        <CardBody className="flex items-end justify-between gap-3 px-4 py-3">
          <div>
            <p className="font-mono text-2xs font-medium uppercase tracking-wider text-fg-muted">
              {labels.complaints_24h}
            </p>
            <p className="mt-1 font-mono text-4xl font-semibold leading-none tabular text-brand-navy">
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

      <Card className="border-border">
        <CardBody className="px-4 py-3">
          <p className="font-mono text-2xs font-medium uppercase tracking-wider text-fg-muted">
            {labels.anomalies_active}
          </p>
          <p
            className={cn(
              'mt-1 font-mono text-4xl font-semibold leading-none tabular',
              kpis.anomalies_active > 0 ? 'text-brand-gold' : 'text-fg',
            )}
          >
            {fmtNum(kpis.anomalies_active, locale)}
          </p>
        </CardBody>
      </Card>

      <Card className="border-border">
        <CardBody className="px-4 py-3">
          <p className="font-mono text-2xs font-medium uppercase tracking-wider text-fg-muted">
            {labels.top_institutions}
          </p>
          <ul className="mt-2 space-y-1 text-xs">
            {kpis.top_institutions.map(inst => (
              <li
                key={inst.institution_id}
                className="flex items-baseline justify-between gap-2 border-b border-border-subtle pb-1 last:border-0 last:pb-0"
              >
                <span className="truncate font-mono tabular text-brand-navy">
                  {inst.institution_name}
                </span>
                <span className="font-mono tabular text-fg-muted">
                  {fmtNum(inst.count_24h, locale)}
                </span>
              </li>
            ))}
            {kpis.top_institutions.length === 0 ? (
              <li className="font-mono text-2xs text-fg-muted">—</li>
            ) : null}
          </ul>
        </CardBody>
      </Card>
    </div>
  );
}
