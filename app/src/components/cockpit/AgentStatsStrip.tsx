// AgentStatsStrip — three tiles showing the live agent layer state.
// Sits under KpiStrip on the cockpit. Empty/zero values fall back to
// the calm-state visual (neutral fg colour) rather than the brand-gold
// "anomaly" colour used in KpiStrip.

import { Card, CardBody } from '@/components/ui';
import type { AgentStats } from '@/types/cockpit';

interface AgentStatsStripProps {
  stats: AgentStats | null | undefined;
  locale: string;
  labels: {
    agent_runs_last_5min: string;
    triaged_today: string;
    high_priority_today: string;
  };
}

function fmtNum(n: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(n);
}

export function AgentStatsStrip({ stats, locale, labels }: AgentStatsStripProps) {
  const data = stats ?? {
    agent_runs_last_5min: 0,
    agents_in_flight: 0,
    complaints_triaged_today: 0,
    high_priority_routes_today: 0,
  };
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      <Tile
        label={labels.agent_runs_last_5min}
        value={fmtNum(data.agent_runs_last_5min, locale)}
      />
      <Tile
        label={labels.triaged_today}
        value={fmtNum(data.complaints_triaged_today, locale)}
      />
      <Tile
        label={labels.high_priority_today}
        value={fmtNum(data.high_priority_routes_today, locale)}
      />
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <Card className="border-border">
      <CardBody className="px-4 py-3">
        <p className="font-mono text-2xs font-medium uppercase tracking-wider text-fg-muted">
          {label}
        </p>
        <p className="mt-1 font-mono text-4xl font-semibold leading-none tabular text-brand-navy">
          {value}
        </p>
      </CardBody>
    </Card>
  );
}
