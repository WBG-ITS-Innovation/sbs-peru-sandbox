// Classification panel — BERT label + confidence bar + top-3 + model
// version. Confidence is rendered as a tabular number to 2 decimals,
// never as a label bucket (one of the WS4 non-droppables).

import { Badge, Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import { cn } from '@/lib/cn';
import type { ClassificationPayload } from '@/types/findings';

interface ClassificationPanelProps {
  classification: ClassificationPayload | null;
  locale: string;
  labels: {
    title: string;
    top_k: string;
    model: string;
  };
}

function confidenceBackground(conf: number | null): string {
  if (conf === null) return 'bg-neutral-100';
  if (conf > 0.8) return 'bg-severity-high-bg';
  if (conf > 0.5) return 'bg-severity-medium-bg';
  return 'bg-severity-low-bg';
}

function confidenceBar(conf: number | null): string {
  if (conf === null) return 'bg-neutral-300';
  if (conf > 0.8) return 'bg-severity-high-border';
  if (conf > 0.5) return 'bg-severity-medium-border';
  return 'bg-severity-low-border';
}

export function ClassificationPanel({
  classification,
  locale,
  labels,
}: ClassificationPanelProps) {
  if (!classification || !classification.label) {
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
  const conf = classification.confidence;
  const nf = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{labels.title}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        <div
          className={cn(
            'rounded-sbs border border-border-subtle p-3',
            confidenceBackground(conf),
          )}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-base font-semibold text-fg">{classification.label}</span>
            <span className="tabular text-base font-semibold text-fg">
              {conf === null ? '—' : nf.format(conf)}
            </span>
          </div>
          {conf !== null ? (
            <div
              className="mt-2 h-1.5 w-full rounded-full bg-surface"
              role="progressbar"
              aria-valuenow={conf}
              aria-valuemin={0}
              aria-valuemax={1}
            >
              <div
                className={cn('h-full rounded-full', confidenceBar(conf))}
                style={{ width: `${Math.max(0, Math.min(1, conf)) * 100}%` }}
              />
            </div>
          ) : null}
          {classification.confidence_degraded ? (
            <p className="mt-1 text-2xs text-severity-high-fg">
              ⚠ Confidence degraded — regex fallback in use.
            </p>
          ) : null}
        </div>

        {classification.sub_patterns.length > 0 ? (
          <div>
            <p className="text-2xs uppercase tracking-wider text-fg-muted">
              {labels.top_k}
            </p>
            <ul className="mt-2 space-y-1">
              {classification.sub_patterns.map((sp, idx) => (
                <li key={idx} className="flex items-center justify-between gap-2 text-sm">
                  <Badge variant="default" className="font-mono text-2xs">
                    {sp.label}
                  </Badge>
                  <span className="tabular text-2xs text-fg-muted">
                    span [{sp.evidence_span[0]}, {sp.evidence_span[1]}]
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {classification.model_version ? (
          <p className="text-2xs text-fg-muted">
            {labels.model}: <code className="font-mono text-fg">{classification.model_version}</code>
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}
