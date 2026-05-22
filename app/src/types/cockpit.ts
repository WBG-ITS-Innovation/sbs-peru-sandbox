// Cockpit data shapes — mirrors api/sbs_api/cockpit/builder.py.
// Kept in this dedicated module so the SSE deltas, the server-component
// fetch, and the client-side merger all reference one type definition.

export type Severity = 'low' | 'medium' | 'high' | 'critical';
export type ConnectionState = 'connecting' | 'connected' | 'disconnected';

export interface ComplaintCardData {
  complaint_id: string;
  institution_id: string;
  received_at: string;
  motivo_code: string;
  product_category: string;
  severity: Severity;
  description_preview: string;
  source: string;
}

export interface TierPanelData {
  tier_label: string;
  institution_id: string;
  institution_name: string;
  descriptor: string;
  recent: ComplaintCardData[];
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

export interface CockpitSnapshot {
  generated_at: string;
  kpis: KpiData;
  tier1: TierPanelData;
  tier2: TierPanelData;
  cross_source: CrossSourceStrip;
  anomalies: AnomalyCardData[];
}
