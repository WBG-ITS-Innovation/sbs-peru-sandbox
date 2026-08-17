// SPDX-License-Identifier: Apache-2.0
// Pinned evidence panel — regex hits + top XGBoost features +
// cross-source channel contributions, side by side. Reads from the
// pinned_evidence block in the approvals detail response.

import { Badge, Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import type { PinnedEvidence } from '@/types/approvals';

interface PinnedEvidencePanelProps {
  evidence: PinnedEvidence;
  locale: string;
  labels: {
    title: string;
    regex_hits: string;
    top_features: string;
    cross_source: string;
  };
}

export function PinnedEvidencePanel({
  evidence,
  locale,
  labels,
}: PinnedEvidencePanelProps) {
  const nf = new Intl.NumberFormat(locale, {
    signDisplay: 'exceptZero',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{labels.title}</CardTitle>
      </CardHeader>
      <CardBody className="grid gap-4 md:grid-cols-3">
        <section>
          <p className="mb-2 text-2xs uppercase tracking-wider text-fg-muted">
            {labels.regex_hits}
          </p>
          {evidence.regex_hits.length === 0 ? (
            <p className="text-2xs text-fg-muted">—</p>
          ) : (
            <ul className="space-y-1">
              {evidence.regex_hits.map((h, i) => (
                <li key={i} className="flex items-baseline gap-1.5 text-2xs">
                  <Badge variant="default" className="font-mono">
                    {h.pattern_id}
                  </Badge>
                  <span className="font-mono italic text-fg">{h.matched_text}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <p className="mb-2 text-2xs uppercase tracking-wider text-fg-muted">
            {labels.top_features}
          </p>
          {evidence.top_features.length === 0 ? (
            <p className="text-2xs text-fg-muted">—</p>
          ) : (
            <ul className="space-y-1">
              {evidence.top_features.map((f, i) => (
                <li key={i} className="flex items-baseline justify-between gap-2 text-2xs">
                  <span className="font-mono text-fg">{f.feature_name}</span>
                  <span className="tabular text-fg">{nf.format(f.contribution)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <p className="mb-2 text-2xs uppercase tracking-wider text-fg-muted">
            {labels.cross_source}
          </p>
          {evidence.cross_source_contributions.length === 0 ? (
            <p className="text-2xs text-fg-muted">—</p>
          ) : (
            <ul className="space-y-1">
              {evidence.cross_source_contributions.map((c, i) => (
                <li key={i} className="flex items-baseline justify-between gap-2 text-2xs">
                  <span className="text-fg">{c.channel}</span>
                  <span className="tabular text-fg">{nf.format(c.contribution)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </CardBody>
    </Card>
  );
}
