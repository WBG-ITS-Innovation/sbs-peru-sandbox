// Narrative panel — renders the complaint text with redaction spans
// visibly marked. Server-renderable since it's pure transform.

import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import { cn } from '@/lib/cn';
import type { AnonymizationPayload, Redaction } from '@/types/findings';

interface NarrativePanelProps {
  text: string;
  redactions: Redaction[];
  anonymization: AnonymizationPayload | null;
  locale: string;
  labels: {
    title: string;
    anonymization: string;
    length: string;
  };
}

function renderWithRedactions(text: string, redactions: Redaction[]): React.ReactNode[] {
  if (!redactions.length) return [text];
  const sorted = [...redactions].sort((a, b) => a.span[0] - b.span[0]);
  const out: React.ReactNode[] = [];
  let pos = 0;
  let key = 0;
  for (const r of sorted) {
    const [start, end] = r.span;
    if (start > pos) out.push(<span key={`t-${key++}`}>{text.slice(pos, start)}</span>);
    out.push(
      <span
        key={`r-${key++}`}
        className="rounded-sbs bg-neutral-200 px-1.5 py-0.5 font-mono text-2xs text-fg-muted"
        title={r.kind}
      >
        [REDACTED:{r.kind}]
      </span>,
    );
    pos = end;
  }
  if (pos < text.length) out.push(<span key={`t-${key++}`}>{text.slice(pos)}</span>);
  return out;
}

export function NarrativePanel({
  text,
  redactions,
  anonymization,
  locale,
  labels,
}: NarrativePanelProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{labels.title}</CardTitle>
        <div className="flex flex-wrap gap-3 text-2xs text-fg-muted">
          <span>
            {labels.length}:{' '}
            <span className="tabular">
              {new Intl.NumberFormat(locale).format(text.length)}
            </span>
          </span>
          {anonymization?.policy_version ? (
            <span>
              {labels.anonymization}:{' '}
              <code className="font-mono text-fg">{anonymization.policy_version}</code>
            </span>
          ) : null}
        </div>
      </CardHeader>
      <CardBody>
        <p className={cn('whitespace-pre-wrap text-sm leading-6 text-fg')}>
          {renderWithRedactions(text, redactions)}
        </p>
      </CardBody>
    </Card>
  );
}
