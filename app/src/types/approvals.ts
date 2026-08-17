// SPDX-License-Identifier: Apache-2.0
// Approvals list + detail types — mirror api/sbs_api/approvals/builder.py.

import type { Severity } from '@/types/cockpit';
import type { FindingDetailResponse } from '@/types/findings';

export type DecisionAction =
  | 'approve'
  | 'approve-with-edits'
  | 'reject'
  | 'send-back-to-analyst';

export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'sent_back';

export interface ApprovalQueueItem {
  id: number;
  complaint_id: string;
  institution_id: string;
  institution_name: string;
  severity: Severity;
  created_at: string;
  time_pending_seconds: number;
  created_by: string;
}

export interface ApprovalKpis {
  pending: number;
  approved_today: number;
  rejected_today: number;
  median_time_to_decision_seconds: number | null;
}

export interface ApprovalsQueueResponse {
  items: ApprovalQueueItem[];
  total_pending: number;
  kpis: ApprovalKpis;
}

export interface PinnedEvidence {
  regex_hits: Array<{
    pattern_id: string;
    label: string;
    span: [number, number];
    matched_text: string;
  }>;
  top_features: Array<{
    feature_name: string;
    contribution: number;
    direction: 'positive' | 'negative';
  }>;
  cross_source_contributions: Array<{
    channel: string;
    value?: number;
    contribution: number;
  }>;
}

export interface DecisionHistory {
  observations: Array<{
    id: number;
    narrative: string;
    approved_by: string;
    approved_at: string;
  }>;
  feedback: Array<{
    id: number;
    decision: 'reject' | 'approve-with-edits';
    rationale: string;
    edit_diff: { before: string; after: string } | null;
    recorded_by: string;
    recorded_at: string;
  }>;
}

export interface ApprovalDetailResponse {
  pending_approval: {
    id: number;
    complaint_id: string;
    agent_run_id: string | null;
    status: ApprovalStatus;
    severity: Severity;
    created_by: string;
    created_at: string;
    decided_at: string | null;
    decided_by: string | null;
    decision_action: DecisionAction | null;
    decision_rationale: string | null;
  };
  finding: FindingDetailResponse;
  pinned_evidence: PinnedEvidence;
  decision_history: DecisionHistory;
}
