// Cockpit data shapes — mirrors api/sbs_api/cockpit/builder.py.
// Kept in this dedicated module so the SSE deltas, the server-component
// fetch, and the client-side merger all reference one type definition.

export type Severity = 'low' | 'medium' | 'high' | 'critical';
export type ConnectionState = 'connecting' | 'connected' | 'disconnected';

export interface UnknownTermRef {
  field_path: string;
  original_value: string;
}

export interface ComplaintCardData {
  complaint_id: string;
  institution_id: string;
  received_at: string;
  motivo_code: string;
  product_category: string;
  severity: Severity;
  description_preview: string;
  source: string;
  // P11 demo-ui-polish overlay. Defaults: false / [] / 0. Older snapshots
  // that predate the migration still render correctly.
  flag_unknown_taxonomy?: boolean;
  unknown_terms?: UnknownTermRef[];
  unknown_terms_total?: number;
}

export type TierVariant = 'tier1' | 'tier2';

export interface TierPanelData {
  tier_label: string;
  // P11 demo-ui-polish — drives Badge variant in the panel header and
  // the ComplaintCard sub-header chip. Older snapshots without this
  // key fall back to 'tier1'.
  tier_variant?: TierVariant;
  institution_id: string;
  institution_name: string;
  descriptor: string;
  recent: ComplaintCardData[];
}

export interface TaxonomyStats {
  normalizations_today: number;
  institutions_affected: number;
  as_of: string;
}

export interface KpiData {
  complaints_24h: number;
  complaints_24h_sparkline: number[];
  anomalies_active: number;
  top_institutions: Array<{
    institution_id: string;
    institution_name: string;
    count_24h: number;
  }>;
}

export interface ChannelContribution {
  channel: string;
  value?: number;
  contribution: number;
}

export interface AnomalyCardData {
  id: string;
  institution_id: string;
  institution_name: string;
  complaint_id: string;
  composite_score: number;
  threshold: number;
  channel_contributions: ChannelContribution[];
  severity: Severity;
  fired_at: string;
  findings_filter: {
    institution_id: string;
    from: string;
  };
}

export interface CrossSourceChannel {
  key: 'complaints' | 'social' | 'indecopi' | 'plavia' | 'internal';
  value: number;
  delta_24h: number;
  sparkline: number[];
}

export interface CrossSourceStrip {
  is_illustrative: boolean;
  channels: CrossSourceChannel[];
}

export interface AgentStats {
  // Count of agent_run rows started in the last 5 minutes. The
  // synchronous pipeline (see ADR 0001) terminates rows inside the
  // ingestion transaction, so an "agents currently running" tile
  // would always read 0; this counter is the honest demo-cadence
  // proxy. ``agents_in_flight`` reports any rows still at status
  // in_progress for completeness.
  agent_runs_last_5min: number;
  agents_in_flight: number;
  complaints_triaged_today: number;
  high_priority_routes_today: number;
}

export interface CockpitSnapshot {
  generated_at: string;
  kpis: KpiData;
  // P12 — optional so older clients (pre-Part-12) still parse the snapshot.
  agent_stats?: AgentStats;
  tier1: TierPanelData;
  tier2: TierPanelData;
  cross_source: CrossSourceStrip;
  anomalies: AnomalyCardData[];
}
