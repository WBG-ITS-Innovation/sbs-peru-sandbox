// SPDX-License-Identifier: Apache-2.0
// Edit-narrative modal — used by Approve with Edits. Two fields:
// the edited narrative (long-form), and the rationale (>= 20 chars,
// same gate as the rationale modal).

'use client';

import { useState } from 'react';

import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui';
import { cn } from '@/lib/cn';

interface EditNarrativeModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (narrative: string, rationale: string) => Promise<void> | void;
  isPending: boolean;
  initialNarrative: string;
  labels: {
    title: string;
    narrative_label: string;
    rationale_label: string;
    min_chars_helper: string;
    confirm: string;
    cancel: string;
  };
}

const MIN_CHARS = 20;

export function EditNarrativeModal({
  open,
  onOpenChange,
  onConfirm,
  isPending,
  initialNarrative,
  labels,
}: EditNarrativeModalProps) {
  const [narrative, setNarrative] = useState(initialNarrative);
  const [rationale, setRationale] = useState('');
  const meetsMin = rationale.trim().length >= MIN_CHARS;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{labels.title}</DialogTitle>
        </DialogHeader>
        <label className="block space-y-1">
          <span className="text-xs font-medium text-fg">{labels.narrative_label}</span>
          <textarea
            rows={6}
            value={narrative}
            onChange={e => setNarrative(e.target.value)}
            className={cn(
              'block w-full rounded-sbs border border-border bg-surface px-3 py-2 text-sm text-fg',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2',
            )}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-xs font-medium text-fg">{labels.rationale_label}</span>
          <textarea
            rows={3}
            value={rationale}
            onChange={e => setRationale(e.target.value)}
            className={cn(
              'block w-full rounded-sbs border border-border bg-surface px-3 py-2 text-sm text-fg',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2',
            )}
          />
          {!meetsMin ? (
            <p className="text-2xs text-severity-high-fg">{labels.min_chars_helper}</p>
          ) : null}
        </label>
        <DialogFooter>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onOpenChange(false)}
            disabled={isPending}
          >
            {labels.cancel}
          </Button>
          <Button
            size="sm"
            disabled={!meetsMin || !narrative.trim() || isPending}
            onClick={() => onConfirm(narrative, rationale.trim())}
          >
            {labels.confirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
