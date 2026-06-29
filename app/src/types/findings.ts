// SPDX-License-Identifier: Apache-2.0
// Findings list + detail types — mirror api/sbs_api/findings/builder.py.

import type { Severity } from '@/types/cockpit';

export type AgentStatus =
  | 'in_progress'
  | 'success'
  | 'partial'
  | 'failed'
  | 'timeout';
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
  // P12 additive fields. Older complaints (with only the legacy
  // classifier agent_run) leave these undefined.
  alternatives?: Array<{ label: string; confidence: number }>;
  source_agent?: 'triage' | 'classifier';
}

export interface ExecutiveSummary {
  text: string | null;
  key_points: string[];
  audience: 'superintendent' | 'supervisor' | null;
  model_version: string | null;
}

export interface AnomalyPayload {
  composite_score: number | null;
  threshold: number | null;
  anomaly_flag: boolean | null;
  contributions: Record<string, number>;
  weights: Record<string, number>;
  model_id?: string | null;
}

export interface SimilarComplaint {
  complaint_id: string;
  institution_id: string;
  received_at: string;
  product_category: string;
  motivo_code: string;
  severity: string;
}

export interface FeaturesPayload {
  score: number | null;
  rank_band: string | null;
  feature_contributions: FeatureContribution[];
  model_version: string | null;
  source_agent?: string;
}

export interface AnonymizationPayload {
  policy_version: string | null;
  redactions: Redaction[];
  status: ToolStatus | null;
}

export interface TaxonomyNormalization {
  field_path: string;
  original_value: string;
  canonical_value: string;
  dictionary_version: string;
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
    flag_unknown_taxonomy?: boolean;
  };
  // P11 demo-ui-polish — taxonomy harmonization panel input. Empty
  // list hides the panel entirely.
  taxonomy_normalizations?: TaxonomyNormalization[];
  taxonomy_dictionary_version?: string | null;
  anonymization: AnonymizationPayload | null;
  classification: ClassificationPayload | null;
  features: FeaturesPayload | null;
  agent_runs: AgentRunSummary[];
  current_narrative: string | null;
  agent_drafted_narrative: string | null;
  // P12 — SynthesisAgent executive brief surfaced under Draft summary.
  // Null until synthesis has run.
  executive_summary?: ExecutiveSummary | null;
  // P12 — InvestigationAgent anomaly contributions + similar complaints.
  anomaly?: AnomalyPayload | null;
  similar_complaints?: SimilarComplaint[];
  latest_draft_id: number | null;
  pending_approval: {
    id: number;
    status: string;
    created_at: string;
  } | null;
}
