// Findings list + detail types — mirror api/sbs_api/findings/builder.py.

import type { Severity } from '@/types/cockpit';

export type AgentStatus = 'success' | 'partial' | 'failed' | 'timeout';
export type ToolStatus = 'success' | 'failed' | 'timeout';

export interface FindingsListItem {
  complaint_id: string;
  institution_id: string;
  institution_name: string;
  received_at: string;
  classification: string;
  confidence: number | null;
  severity: Severity;
  source: string;
  drafted_by_agent: boolean;
}

export interface FindingsListResponse {
  items: FindingsListItem[];
  total: number;
  filters_applied: Record<string, string | null>;
}

export interface Redaction {
  kind: string;
  span: [number, number];
}

export interface FeatureContribution {
  feature_name: string;
  contribution: number;
  direction: 'positive' | 'negative';
}

export interface ToolCall {
  tool_name: string;
  tool_version: string;
  started_at: string;
  ended_at: string;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  status: ToolStatus;
  error: { code: string; message: string } | null;
}

export interface AgentRunSummary {
  id: string;
  agent_name: string;
  agent_version: string;
  started_at: string;
  ended_at: string | null;
  status: AgentStatus;
  tool_calls: ToolCall[];
  final_output: Record<string, unknown> | null;
  error: { code: string; message: string; tool_name?: string } | null;
}

export interface ClassificationPayload {
  label: string | null;
  confidence: number | null;
  confidence_degraded: boolean;
  sub_patterns: Array<{ label: string; evidence_span: [number, number] }>;
  rank_band: string | null;
  model_version: string | null;
}

export interface FeaturesPayload {
  score: number | null;
  rank_band: string | null;
  feature_contributions: FeatureContribution[];
  model_version: string | null;
}

export interface AnonymizationPayload {
  policy_version: string | null;
  redactions: Redaction[];
  status: ToolStatus | null;
}

export interface FindingDetailResponse {
  complaint: {
    complaint_id: string;
    institution_id: string;
    institution_name: string;
    received_at: string;
    source: string;
    motivo_code: string;
    product_category: string;
    severity: Severity;
    channel: string;
    complainant_age_range: string;
    complainant_district: string;
    narrative_text: string;
    narrative_length: number;
    // P11 demo-ready overlay — Annex 1-A resolution-side fields,
    // optional because they're only populated when the institution
    // sends them. ``descripcion_resolucion`` is redacted text.
    fecha_resolucion?: string | null;
    tipo_resolucion?: string | null;
    descripcion_resolucion?: string | null;
    estado_reclamo?: string | null;
    monto_pendiente?: string | null;
  };
  anonymization: AnonymizationPayload | null;
  classification: ClassificationPayload | null;
  features: FeaturesPayload | null;
  agent_runs: AgentRunSummary[];
  current_narrative: string | null;
  agent_drafted_narrative: string | null;
  latest_draft_id: number | null;
  pending_approval: {
    id: number;
    status: string;
    created_at: string;
  } | null;
}
