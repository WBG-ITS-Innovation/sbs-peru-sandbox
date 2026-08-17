// SPDX-License-Identifier: Apache-2.0
// Feature importance panel — XGBoost SHAP-style horizontal bars.
// Positive contributions in cyan (brand accent), negative in gold (the
// attention marker token). Top 8 features by absolute contribution.

import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import { cn } from '@/lib/cn';
import type { FeaturesPayload } from '@/types/findings';

interface FeatureImportancePanelProps {
  features: FeaturesPayload | null;
  locale: string;
  labels: {
    title: string;
    model: string;
    rank_band: string;
  };
}

export function FeatureImportancePanel({
  features,
  locale,
  labels,
}: FeatureImportancePanelProps) {
  if (!features || features.feature_contributions.length === 0) {
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
  const sorted = [...features.feature_contributions]
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .slice(0, 8);
  const maxAbs = Math.max(...sorted.map(c => Math.abs(c.contribution)), 0.01);

  const nf = new Intl.NumberFormat(locale, {
    signDisplay: 'exceptZero',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{labels.title}</CardTitle>
        <div className="flex flex-wrap gap-3 text-2xs text-fg-muted">
          {features.rank_band ? (
            <span>
              {labels.rank_band}: <code className="font-mono text-fg">{features.rank_band}</code>
            </span>
          ) : null}
          {features.model_version ? (
            <span>
              {labels.model}: <code className="font-mono text-fg">{features.model_version}</code>
            </span>
          ) : null}
        </div>
      </CardHeader>
      <CardBody>
        <ul className="space-y-2">
          {sorted.map(c => {
            const width = (Math.abs(c.contribution) / maxAbs) * 100;
            const positive = c.direction === 'positive';
            return (
              <li key={c.feature_name} className="flex items-center gap-2">
                <span className="w-56 truncate font-mono text-2xs text-fg" title={c.feature_name}>
                  {c.feature_name}
                </span>
                <div className="relative h-3 flex-1 overflow-hidden rounded-sbs bg-surface-subtle">
                  <div
                    className={cn(
                      'absolute inset-y-0',
                      positive ? 'bg-brand-cyan left-1/2' : 'bg-brand-gold right-1/2',
                    )}
                    style={{ width: `${width / 2}%` }}
                  />
                  <div className="absolute inset-y-0 left-1/2 w-px bg-border" aria-hidden="true" />
                </div>
                <span className="w-16 text-right tabular text-2xs text-fg">
                  {nf.format(c.contribution)}
                </span>
              </li>
            );
          })}
        </ul>
      </CardBody>
    </Card>
  );
}
