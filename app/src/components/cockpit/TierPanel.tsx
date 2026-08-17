// SPDX-License-Identifier: Apache-2.0
// TierPanel — one of the two panels in the Tier 1 / Tier 2 hero view.
// Both panels render the same component identically; the difference is
// the source label, the institution name, and the velocity descriptor.
// Header treatment follows the Claude Design artifact: institution
// name in font-mono brand-navy, tier label as a small pill, descriptor
// as a faint mono sub-line. The list of recent complaints below is the
// real DB/SSE-backed data — no UI change to that.

import { Badge, Card, CardBody, CardHeader, EmptyState } from '@/components/ui';
import { ComplaintCard } from './ComplaintCard';
import type { TierPanelData, TierVariant } from '@/types/cockpit';

interface TierPanelProps {
  panel: TierPanelData;
  locale: string;
  emptyText: { title: string; body: string; primary: { label: string; href: string } };
  showOnlyUnknownTaxonomy?: boolean;
  unknownPillLabel?: string;
}

export function TierPanel({
  panel,
  locale,
  emptyText,
  showOnlyUnknownTaxonomy = false,
  unknownPillLabel,
}: TierPanelProps) {
  const variant: TierVariant = panel.tier_variant ?? 'tier1';
  const visible = showOnlyUnknownTaxonomy
    ? panel.recent.filter(c => c.flag_unknown_taxonomy === true)
    : panel.recent;
  return (
    <Card className="border-border">
      <CardHeader className="border-b border-border px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-mono text-sm font-semibold tabular text-brand-navy">
            {panel.institution_name}
          </h2>
          <Badge variant={variant} className="uppercase tracking-wider">
            {panel.tier_label}
          </Badge>
        </div>
        <p className="mt-1 font-mono text-2xs uppercase tracking-wider text-fg-muted">
          {panel.descriptor}
        </p>
      </CardHeader>
      <CardBody className="space-y-2 p-3">
        {visible.length === 0 ? (
          <EmptyState
            icon={<span aria-hidden="true">∅</span>}
            title={emptyText.title}
            body={emptyText.body}
            primaryAction={emptyText.primary}
          />
        ) : (
          visible.map(c => (
            <ComplaintCard
              key={c.complaint_id}
              complaint={c}
              locale={locale}
              unknownPillLabel={unknownPillLabel}
            />
          ))
        )}
      </CardBody>
    </Card>
  );
}
