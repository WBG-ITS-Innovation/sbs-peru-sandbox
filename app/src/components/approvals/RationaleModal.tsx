// Rationale modal — used by Reject and Send-back. 20-character
// minimum, live character counter, submit disabled below threshold.
// Helper text reads "Mínimo 20 caracteres / Minimum 20 characters"
// per the WS5 non-droppable.

'use client';

import { useState } from 'react';

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui';
import { cn } from '@/lib/cn';

interface RationaleModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (rationale: string) => Promise<void> | void;
  isPending: boolean;
  labels: {
    title: string;
    description: string;
    label: string;
    placeholder: string;
    min_chars_helper: string;
    char_count_template: string;        // "{count} of minimum 20"
    confirm: string;
    cancel: string;
  };
}

const MIN_CHARS = 20;

export function RationaleModal({
  open,
  onOpenChange,
  onConfirm,
  isPending,
  labels,
}: RationaleModalProps) {
  const [text, setText] = useState('');
  const meetsMin = text.trim().length >= MIN_CHARS;
  const count = text.length;
  const charCount = labels.char_count_template.replace('{count}', String(count));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{labels.title}</DialogTitle>
          <DialogDescription>{labels.description}</DialogDescription>
        </DialogHeader>
        <label className="block space-y-1">
          <span className="text-xs font-medium text-fg">{labels.label}</span>
          <textarea
            rows={4}
            value={text}
            onChange={e => setText(e.target.value)}
            placeholder={labels.placeholder}
            aria-describedby="rationale-helper"
            className={cn(
              'block w-full rounded-sbs border border-border bg-surface px-3 py-2 text-sm text-fg',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2',
            )}
          />
          <div
            id="rationale-helper"
            className={cn(
              'flex justify-between text-2xs',
              meetsMin ? 'text-fg-muted' : 'text-severity-high-fg',
            )}
          >
            <span>{meetsMin ? ' ' : labels.min_chars_helper}</span>
            <span className="tabular">{charCount}</span>
          </div>
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
            disabled={!meetsMin || isPending}
            onClick={() => onConfirm(text.trim())}
          >
            {labels.confirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
