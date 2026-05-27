// CockpitClient — the client-side wrapper that merges the server-
// rendered snapshot with SSE deltas. The pieces that mutate live
// (tier panels, anomalies) re-render from this component's state;
// pieces that are stable for a snapshot (KPIs aggregate) re-render
// on a delta but use the same data the server fetched.

'use client';

import { useCallback, useState } from 'react';

import { useSSE, type SSEMessage } from '@/hooks/useSSE';
import type {
  CockpitSnapshot,
  ComplaintCardData,
  TaxonomyStats,
} from '@/types/cockpit';

import { AnomalyCard } from './AnomalyCard';
import { CrossSourceStrip } from './CrossSourceStrip';
import { KpiStrip } from './KpiStrip';
import { LiveIngestionPanel } from './LiveIngestionPanel';
import { TaxonomyStatsTile } from './TaxonomyStatsTile';
import { TierPanel } from './TierPanel';
import {
  TIER1_INSTITUTION_ID,
  TIER2_INSTITUTION_ID,
} from './ids';

interface Labels {
  locale: string;
  kpis: {
    complaints_24h: string;
    anomalies_active: string;
    top_institutions: string;
  };
  crossSource: {
    title: string;
    illustrative: string;
    channels: Record<string, string>;
  };
  anomaly: {
    threshold: string;
    composite: string;
    why_fired: string;
    channels: string;
    open_findings: string;
  };
  emptyTier1: { title: string; body: string; primary: { label: string; href: string } };
  emptyTier2: { title: string; body: string; primary: { label: string; href: string } };
  emptyAnomalies: { title: string; body: string };
  liveIngestion: React.ComponentProps<typeof LiveIngestionPanel>['labels'];
  taxonomy: {
    tile_title: string;
    tile_as_of_prefix: string;
    tile_summary_one: string;
    tile_summary_many: string;
    filter_label: string;
    unknown_pill: string;
  };
}

interface CockpitClientProps {
  initialSnapshot: CockpitSnapshot;
  initialTaxonomyStats: TaxonomyStats;
  labels: Labels;
  csrfToken: string;
}

function reduceCockpit(state: CockpitSnapshot, message: SSEMessage<unknown>): CockpitSnapshot {
  if (message.event === 'snapshot') {
    // The initial snapshot is already-applied (id=0); but if the server
    // sends a fresh snapshot (e.g., after resync) we replace state.
    return (message.data as CockpitSnapshot) ?? state;
  }
  if (message.event === 'complaint.received') {
    const c = message.data as ComplaintCardData;
    const panel = c.institution_id === TIER1_INSTITUTION_ID ? 'tier1' : 'tier2';
    if (c.institution_id !== TIER1_INSTITUTION_ID && c.institution_id !== TIER2_INSTITUTION_ID) {
      return state;
    }
    const target = state[panel];
    return {
      ...state,
      [panel]: {
        ...target,
        recent: [c, ...target.recent].slice(0, 6),
      },
      kpis: {
        ...state.kpis,
        complaints_24h: state.kpis.complaints_24h + 1,
      },
    };
  }
  if (message.event === 'anomaly.detected') {
    return {
      ...state,
      anomalies: [
        message.data as CockpitSnapshot['anomalies'][number],
        ...state.anomalies,
      ],
      kpis: {
        ...state.kpis,
        anomalies_active: state.kpis.anomalies_active + 1,
      },
    };
  }
  return state;
}

export function CockpitClient({
  initialSnapshot,
  initialTaxonomyStats,
  labels,
  csrfToken,
}: CockpitClientProps) {
  const reduce = useCallback(reduceCockpit, []);
  const { state } = useSSE<CockpitSnapshot>({
    url: '/app/api/sse/cockpit',
    initialState: initialSnapshot,
    reduce,
  });
  const [showOnlyUnknownTaxonomy, setShowOnlyUnknownTaxonomy] = useState(false);

  const summaryFor = (n: number, m: number): string =>
    (n === 1 ? labels.taxonomy.tile_summary_one : labels.taxonomy.tile_summary_many)
      .replace('{n}', new Intl.NumberFormat(labels.locale).format(n))
      .replace('{m}', new Intl.NumberFormat(labels.locale).format(m));

  return (
    <div className="space-y-3">
      <KpiStrip kpis={state.kpis} locale={labels.locale} labels={labels.kpis} />

      {state.anomalies.length > 0 ? (
        <div className="space-y-2">
          {state.anomalies.map(a => (
            <AnomalyCard
              key={a.id}
              anomaly={a}
              locale={labels.locale}
              labels={labels.anomaly}
            />
          ))}
        </div>
      ) : null}

      <div className="grid gap-3 md:grid-cols-[2fr_1fr] md:items-stretch">
        <div className="flex items-center justify-end gap-2 rounded-sbs border border-border-subtle bg-surface px-3 py-2 text-xs">
          <label className="inline-flex cursor-pointer items-center gap-2 font-mono uppercase tracking-wider text-fg-muted">
            <input
              type="checkbox"
              checked={showOnlyUnknownTaxonomy}
              onChange={e => setShowOnlyUnknownTaxonomy(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-border accent-brand-gold"
            />
            {labels.taxonomy.filter_label}
          </label>
        </div>
        <TaxonomyStatsTile
          stats={initialTaxonomyStats}
          locale={labels.locale}
          labels={{
            title: labels.taxonomy.tile_title,
            summary: summaryFor,
            as_of_prefix: labels.taxonomy.tile_as_of_prefix,
          }}
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-[1.5fr_1fr]">
        <TierPanel
          panel={state.tier1}
          locale={labels.locale}
          emptyText={labels.emptyTier1}
          showOnlyUnknownTaxonomy={showOnlyUnknownTaxonomy}
          unknownPillLabel={labels.taxonomy.unknown_pill}
        />
        <TierPanel
          panel={state.tier2}
          locale={labels.locale}
          emptyText={labels.emptyTier2}
          showOnlyUnknownTaxonomy={showOnlyUnknownTaxonomy}
          unknownPillLabel={labels.taxonomy.unknown_pill}
        />
      </div>

      <LiveIngestionPanel labels={labels.liveIngestion} csrfToken={csrfToken} />

      <CrossSourceStrip
        strip={state.cross_source}
        locale={labels.locale}
        labels={labels.crossSource}
      />
    </div>
  );
}
