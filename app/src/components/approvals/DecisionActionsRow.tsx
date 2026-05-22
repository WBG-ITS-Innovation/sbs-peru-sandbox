// Four decision buttons — Approve, Approve with edits, Reject,
// Send back to analyst. Approve fires directly (with a server-side
// audit); the other three open their respective modals.
//
// Idempotency on duplicate POST is server-side (the route returns
// idempotent_replay=true). The button stays interactive after a
// click; a second click hits the same endpoint and the UI reflects
// the (unchanged) decision.

'use client';

import { useState, useTransition } from 'react';

import { Badge, Button } from '@/components/ui';
import type { ApprovalStatus, DecisionAction } from '@/types/approvals';

import { EditNarrativeModal } from './EditNarrativeModal';
import { RationaleModal } from './RationaleModal';

interface Labels {
  approve: string;
  approve_with_edits: string;
  reject: string;
  send_back: string;
  confirm: string;
  cancel: string;
  already_decided: string;
  decision_recorded: string;
  reject_modal: {
    title: string;
    description: string;
    label: string;
    placeholder: string;
    min_chars_helper: string;
    char_count_template: string;
  };
  send_back_modal: {
    title: string;
    description: string;
    label: string;
    placeholder: string;
    min_chars_helper: string;
    char_count_template: string;
  };
  edit_modal: {
    title: string;
    narrative_label: string;
    rationale_label: string;
    min_chars_helper: string;
  };
}

interface DecisionActionsRowProps {
  approvalId: number;
  currentNarrative: string;
  initialStatus: ApprovalStatus;
  initialDecisionAction: DecisionAction | null;
  csrfToken: string;
  labels: Labels;
}

export function DecisionActionsRow({
  approvalId,
  currentNarrative,
  initialStatus,
  initialDecisionAction,
  csrfToken,
  labels,
}: DecisionActionsRowProps) {
  const [status, setStatus] = useState<ApprovalStatus>(initialStatus);
  const [decisionAction, setDecisionAction] = useState<DecisionAction | null>(
    initialDecisionAction,
  );
  const [openModal, setOpenModal] = useState<'reject' | 'send-back' | 'edit' | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  if (status !== 'pending') {
    return (
      <div className="flex items-center gap-2">
        <Badge variant="in-review">
          {labels.already_decided} · {decisionAction ?? '—'}
        </Badge>
      </div>
    );
  }

  function fire(action: DecisionAction, body: Record<string, unknown>) {
    const path =
      action === 'approve'
        ? 'approve'
        : action === 'approve-with-edits'
          ? 'approve-with-edits'
          : action === 'reject'
            ? 'reject'
            : 'send-back';
    startTransition(async () => {
      setError(null);
      const response = await fetch(`/app/api/approvals/${approvalId}/${path}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-SBS-CSRF': csrfToken,
        },
        credentials: 'include',
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        setError(`HTTP ${response.status}`);
        return;
      }
      const data = await response.json();
      setStatus(data.status);
      setDecisionAction(data.decision_action);
      setOpenModal(null);
    });
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          onClick={() => fire('approve', {})}
          disabled={isPending}
        >
          {labels.approve}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setOpenModal('edit')}
          disabled={isPending}
        >
          {labels.approve_with_edits}
        </Button>
        <Button
          size="sm"
          variant="destructive"
          onClick={() => setOpenModal('reject')}
          disabled={isPending}
        >
          {labels.reject}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setOpenModal('send-back')}
          disabled={isPending}
        >
          {labels.send_back}
        </Button>
        {error ? (
          <span role="alert" className="text-2xs text-severity-high-fg">
            {error}
          </span>
        ) : null}
      </div>

      <RationaleModal
        open={openModal === 'reject'}
        onOpenChange={o => setOpenModal(o ? 'reject' : null)}
        isPending={isPending}
        labels={{
          ...labels.reject_modal,
          confirm: labels.confirm,
          cancel: labels.cancel,
        }}
        onConfirm={rationale => fire('reject', { rationale })}
      />
      <RationaleModal
        open={openModal === 'send-back'}
        onOpenChange={o => setOpenModal(o ? 'send-back' : null)}
        isPending={isPending}
        labels={{
          ...labels.send_back_modal,
          confirm: labels.confirm,
          cancel: labels.cancel,
        }}
        onConfirm={note => fire('send-back-to-analyst', { note })}
      />
      <EditNarrativeModal
        open={openModal === 'edit'}
        onOpenChange={o => setOpenModal(o ? 'edit' : null)}
        isPending={isPending}
        initialNarrative={currentNarrative}
        labels={{
          ...labels.edit_modal,
          confirm: labels.confirm,
          cancel: labels.cancel,
        }}
        onConfirm={(edited_narrative, rationale) =>
          fire('approve-with-edits', { edited_narrative, rationale })
        }
      />
    </>
  );
}
