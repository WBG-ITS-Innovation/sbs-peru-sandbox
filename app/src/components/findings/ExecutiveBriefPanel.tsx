// SPDX-License-Identifier: Apache-2.0
// Executive brief sub-panel — plain-Spanish summary from SynthesisAgent.
// Sits under Draft summary. Collapsed by default; the head/supervisor
// expands to see the brief Superintendent or the Supervisor would read.

'use client';

import { useState } from 'react';

import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import type { ExecutiveSummary } from '@/types/findings';

interface ExecutiveBriefPanelProps {
  summary: ExecutiveSummary | null | undefined;
  labels: {
    title: string;
    show: string;
    hide: string;
    audience: string;
    key_points: string;
    model: string;
    empty: string;
  };
}

export function ExecutiveBriefPanel({ summary, labels }: ExecutiveBriefPanelProps) {
  const [open, setOpen] = useState(false);
  const hasText = Boolean(summary && summary.text);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle>{labels.title}</CardTitle>
          <button
            type="button"
            onClick={() => setOpen(v => !v)}
            className="text-xs text-fg-link hover:underline"
            aria-expanded={open}
          >
            {open ? labels.hide : labels.show}
          </button>
        </div>
      </CardHeader>
      {open ? (
        <CardBody className="space-y-3">
          {!hasText ? (
            <p className="text-sm text-fg-muted">{labels.empty}</p>
          ) : (
            <>
              <p className="whitespace-pre-line text-sm text-fg">{summary!.text}</p>
              {summary!.key_points.length > 0 ? (
                <div>
                  <p className="text-2xs uppercase tracking-wider text-fg-muted">
                    {labels.key_points}
                  </p>
                  <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-fg">
                    {summary!.key_points.map((kp, idx) => (
                      <li key={idx}>{kp}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              <div className="flex flex-wrap gap-3 text-2xs text-fg-muted">
                {summary!.audience ? (
                  <span>
                    {labels.audience}:{' '}
                    <code className="font-mono text-fg">{summary!.audience}</code>
                  </span>
                ) : null}
                {summary!.model_version ? (
                  <span>
                    {labels.model}:{' '}
                    <code className="font-mono text-fg">{summary!.model_version}</code>
                  </span>
                ) : null}
              </div>
            </>
          )}
        </CardBody>
      ) : null}
    </Card>
  );
}
