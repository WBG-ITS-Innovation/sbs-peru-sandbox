// SPDX-License-Identifier: Apache-2.0
// Response shapes for the persona dashboards (P-RESHAPE-10). Field names
// mirror the FastAPI responses captured from the live backend; optional
// fields reflect persona-scoped stripping (e.g. SBS IT receives no
// character display_name; the Superintendent receives no recent_runs).

export interface AgentRunSummary {
  audit_id: string;
  underlying_agent_id: string;
  started_at: string;
  duration_ms: number;
  status: string;
  model_id: string | null;
}

export interface AgentBlock {
  agent_id: string;
  is_fi_facing: boolean;
  status: string; // IDLE | RUNNING | DEGRADED
  total_runs_in_window: number;
  success_rate: number | null;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  last_run_at: string | null;
  display_name_es?: string;
  display_name_en?: string;
  character_avatar_id?: string | null;
  tagline_es?: string;
  tagline_en?: string;
  recent_runs?: AgentRunSummary[];
}

export interface AgentsResponse {
  agents: AgentBlock[];
  window: string;
  computed_at: string;
}

export interface ActionDef {
  action_id: string;
  label_es: string;
  label_en: string;
  description_es?: string;
  description_en?: string;
  endpoint: string;
  scope: string;
  requires_rationale_chars: number;
}

export interface ActionsResponse {
  actions: ActionDef[];
  total: number;
}

export interface TaskItem {
  task_id: string;
  created_at: string;
  created_by_user_id: string;
  created_by_persona: string;
  assigned_to_user_id: string | null;
  assigned_to_persona: string;
  task_type: string;
  ref_type: string;
  ref_id: string;
  rationale: string;
  state: string;
  response: string | null;
}

export interface TasksResponse {
  items: TaskItem[];
  total: number;
}

export interface ChatCitation {
  tool: string;
  parameters: Record<string, unknown>;
  query_hash: string;
  row_ids_returned: string[];
}

export interface ChatMessage {
  message_id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: { items: ChatCitation[] } | null;
  model_id: string | null;
  created_at: string;
}

export interface ChatSession {
  session_id: string;
  persona: string;
  ended_at: string | null;
  messages: ChatMessage[];
}

export interface SuggestedQuestions {
  persona: string;
  questions: string[];
}

export interface FindingRow {
  complaint_id: string;
  institution_id: string;
  institution_name: string;
  received_at: string;
  classification: string;
  confidence: number | null;
  severity: string;
  source: string;
  drafted_by_agent: boolean;
}

export interface FindingsResponse {
  items: FindingRow[];
  total?: number;
}

export interface ExplainEntry {
  surface_id: string;
  es: string;
  en: string;
  source_agent: string | null;
  source_rule: string | null;
  source_data_window: string | null;
}

export interface IngestionLagItem {
  institution_id: string;
  last_received_at: string;
  expected_cadence_hours: number;
  lag_hours: number;
  status: 'GREEN' | 'AMBER' | 'RED';
}

export interface AgentHealthItem {
  agent: string;
  runs_24h: number;
  success_rate_24h: number;
  last_run_at: string | null;
  p50_latency_ms: number;
  p95_latency_ms: number;
}

export interface WebhookHealth {
  total: number;
  by_status: Record<string, number>;
  attempt_histogram: Record<string, number>;
  last_failures: Array<{
    delivery_id: string;
    institution_id: string;
    attempts: number;
    failure_reason: string;
  }>;
}

export interface QueueDepth {
  queues: Record<string, number | string>;
}

export interface ErrorTailItem {
  agent: string;
  status: string;
  error_code: string | null;
  occurred_at: string;
}

export interface ErrorTail {
  errors: ErrorTailItem[];
}

export interface SectorBroadcastSummary {
  awaiting_co_approval: number;
  awaiting_my_secondary_approval: number;
  items: Array<{
    broadcast_id: string;
    status: string;
    urgency: string;
    target_fi_count: number;
    threat_indicators: string[];
    response_deadline: string;
  }>;
}

export interface ExecPatternsSummary {
  // top_patterns_summary — aggregate, no per-complaint detail.
  [key: string]: unknown;
}
