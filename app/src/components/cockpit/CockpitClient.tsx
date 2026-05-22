// CockpitClient — the client-side wrapper that merges the server-
// rendered snapshot with SSE deltas. The pieces that mutate live
// (tier panels, anomalies) re-render from this component's state;
// pieces that are stable for a snapshot (KPIs aggregate) re-render
// on a delta but use the same data the server fetched.

'use client';

import { useCallback } from 'react';

import { useSSE, type SSEMessage } from '@/hooks/useSSE';
import type { CockpitSnapshot, ComplaintCardData } from '@/types/cockpit';

import { AnomalyCard } from './AnomalyCard';
import { ConnectionStateDot } from './ConnectionStateDot';
import { CrossSourceStrip } from './CrossSourceStrip';
import { KpiStrip } from './KpiStrip';
import { TierPanel } from './TierPanel';
import {
  TIER1_INSTITUTION_ID,
  TIER2_INSTITUTION_ID,
} from './ids';

interface Labels {
  locale: string;
  connectionLabel: {
    connecting: string;
    connected: string;
    disconnected: string;
  };
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
}

interface CockpitClientProps {
  initialSnapshot: CockpitSnapshot;
  labels: Labels;
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

export function CockpitClient({ initialSnapshot, labels }: CockpitClientProps) {
  const reduce = useCallback(reduceCockpit, []);
  const { state, connectionState } = useSSE<CockpitSnapshot>({
    url: '/app/api/sse/cockpit',
    initialState: initialSnapshot,
    reduce,
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-fg">{labels.kpis.complaints_24h}</h1>
        <ConnectionStateDot state={connectionState} label={labels.connectionLabel} />
      </div>

      <KpiStrip kpis={state.kpis} locale={labels.locale} labels={labels.kpis} />

      {state.anomalies.length > 0 ? (
        <div className="space-y-3">
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

      <div className="grid gap-4 lg:grid-cols-2">
        <TierPanel
          panel={state.tier1}
          locale={labels.locale}
          emptyText={labels.emptyTier1}
        />
        <TierPanel
          panel={state.tier2}
          locale={labels.locale}
          emptyText={labels.emptyTier2}
        />
      </div>

      <CrossSourceStrip
        strip={state.cross_source}
        locale={labels.locale}
        labels={labels.crossSource}
      />
    </div>
  );
}
