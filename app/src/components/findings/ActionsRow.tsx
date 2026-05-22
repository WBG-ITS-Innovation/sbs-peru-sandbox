// Actions row — Send to Approvals + Mark false positive (stub) +
// Assign (visible-but-disabled tooltip per the WS4 drop ladder).
// Lives below the draft editor on the detail page.

'use client';

import { useState, useTransition } from 'react';

import {
  Badge,
  Button,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui';
import type { Severity } from '@/types/cockpit';

interface ActionsRowProps {
  complaintId: string;
  severity: Severity;
  csrfToken: string;
  actorId: string;
  agentRunId: string | null;
  pendingApprovalId: number | null;
  isHead: boolean;
  labels: {
    send_to_approvals: string;
    mark_false_positive: string;
    assign: string;
    already_pending: string;
    assignment_via_api: string;
  };
}

export function ActionsRow({
  complaintId,
  severity,
  csrfToken,
  actorId,
  agentRunId,
  pendingApprovalId,
  isHead,
  labels,
}: ActionsRowProps) {
  const [pendingId, setPendingId] = useState<number | null>(pendingApprovalId);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function sendToApprovals() {
    if (pendingId) return;
    startTransition(async () => {
      setError(null);
      const response = await fetch(
        `/app/api/findings/${encodeURIComponent(complaintId)}/send-to-approvals`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-SBS-CSRF': csrfToken,
          },
          credentials: 'include',
          body: JSON.stringify({ severity, actor_id: actorId, agent_run_id: agentRunId }),
        },
      );
      if (!response.ok) {
        setError(`HTTP ${response.status}`);
        return;
      }
      const body = await response.json();
      setPendingId(body.id);
    });
  }

  return (
    <TooltipProvider>
      <div className="flex flex-wrap items-center gap-2">
        {pendingId ? (
          <Badge variant="in-review">
            {labels.already_pending} #{pendingId}
          </Badge>
        ) : (
          <Button size="sm" onClick={sendToApprovals} disabled={isPending}>
            {labels.send_to_approvals}
          </Button>
        )}

        <Button size="sm" variant="outline" disabled>
          {labels.mark_false_positive}
        </Button>

        {isHead ? null : (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <Button size="sm" variant="outline" disabled>
                  {labels.assign}
                </Button>
              </span>
            </TooltipTrigger>
            <TooltipContent>{labels.assignment_via_api}</TooltipContent>
          </Tooltip>
        )}

        {error ? (
          <span role="alert" className="text-2xs text-severity-high-fg">
            {error}
          </span>
        ) : null}
      </div>
    </TooltipProvider>
  );
}
