// SPDX-License-Identifier: Apache-2.0
// Agent reasoning panel — vertical timeline. Reads agent_runs for the
// complaint and renders each tool_call as a step. Status icons + colors
// distinguish success / failed / timeout per WS4 non-droppable. The
// partial-run case (BERT timeout → regex fallback) shows the partial
// pill on the parent run + the per-tool statuses inside.

import {
  Activity,
  AlertOctagon,
  CheckCircle,
  Clock,
  XCircle,
  type LucideIcon,
} from 'lucide-react';

import { Badge, Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import { cn } from '@/lib/cn';
import type { AgentRunSummary, ToolStatus } from '@/types/findings';

interface AgentReasoningPanelProps {
  runs: AgentRunSummary[];
  locale: string;
  labels: {
    title: string;
    status: {
      in_progress: string;
      success: string;
      partial: string;
      failed: string;
      timeout: string;
    };
  };
}

const TOOL_STATUS_ICON: Record<ToolStatus, LucideIcon> = {
  success: CheckCircle,
  failed: XCircle,
  timeout: Clock,
};

const TOOL_STATUS_CLASS: Record<ToolStatus, string> = {
  success: 'text-severity-low-fg',
  failed: 'text-severity-critical-fg',
  timeout: 'text-severity-high-fg',
};

const RUN_STATUS_VARIANT: Record<
  AgentRunSummary['status'],
  'low' | 'medium' | 'high' | 'critical'
> = {
  in_progress: 'medium',
  success: 'low',
  partial: 'medium',
  failed: 'critical',
  timeout: 'high',
};

function fmtElapsed(start: string, end: string | null, locale: string): string {
  if (!end) return '…';
  const s = new Date(start).getTime();
  const e = new Date(end).getTime();
  const ms = Math.max(0, e - s);
  const nf = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
  if (ms < 1000) return `${nf.format(ms)} ms`;
  return `${nf.format(ms / 1000)} s`;
}

export function AgentReasoningPanel({ runs, locale, labels }: AgentReasoningPanelProps) {
  if (runs.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{labels.title}</CardTitle>
        </CardHeader>
        <CardBody>
          <p className="text-sm text-fg-muted">—</p>
        </CardBody>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>{labels.title}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-5">
        {runs.map(run => (
          <section key={run.id} className="space-y-2">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-fg-muted" aria-hidden="true" />
              <span className="text-sm font-semibold text-fg">{run.agent_name}</span>
              <code className="font-mono text-2xs text-fg-muted">{run.agent_version}</code>
              <Badge variant={RUN_STATUS_VARIANT[run.status]} className="ml-auto">
                {labels.status[run.status]}
              </Badge>
            </div>
            <ol className="ml-2 space-y-1 border-l border-border-subtle pl-3">
              {run.tool_calls.map((tc, idx) => {
                const Icon = TOOL_STATUS_ICON[tc.status] ?? AlertOctagon;
                return (
                  <li
                    key={`${run.id}-${idx}`}
                    className="flex items-center gap-2 text-2xs"
                  >
                    <Icon
                      className={cn('h-3.5 w-3.5', TOOL_STATUS_CLASS[tc.status])}
                      aria-hidden="true"
                    />
                    <code className="font-mono text-fg">{tc.tool_name}</code>
                    <span className="text-fg-muted">
                      <code className="font-mono">{tc.tool_version}</code>
                    </span>
                    <span className="ml-auto tabular text-fg-muted">
                      {fmtElapsed(tc.started_at, tc.ended_at, locale)}
                    </span>
                    {tc.error ? (
                      <span className="ml-2 font-mono text-severity-critical-fg">
                        {tc.error.code}
                      </span>
                    ) : null}
                  </li>
                );
              })}
              {run.error ? (
                <li className="mt-1 rounded-sbs bg-severity-high-bg px-2 py-1 text-2xs text-severity-high-fg">
                  <code className="font-mono">{run.error.code}</code> — {run.error.message}
                </li>
              ) : null}
            </ol>
          </section>
        ))}
      </CardBody>
    </Card>
  );
}
