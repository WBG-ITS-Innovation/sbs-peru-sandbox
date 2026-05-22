// TierPanel — one of the two panels in the Tier 1 / Tier 2 side-by-
// side hero view. Both panels render the same component identically;
// the difference is the source label, the institution name, and the
// velocity descriptor.

import { Card, CardBody, CardHeader, EmptyState } from '@/components/ui';
import { ComplaintCard } from './ComplaintCard';
import type { TierPanelData } from '@/types/cockpit';

interface TierPanelProps {
  panel: TierPanelData;
  locale: string;
  emptyText: { title: string; body: string; primary: { label: string; href: string } };
}

export function TierPanel({ panel, locale, emptyText }: TierPanelProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-base font-semibold text-fg">{panel.institution_name}</h2>
          <span className="text-2xs font-medium uppercase tracking-wider text-fg-muted">
            {panel.tier_label}
          </span>
        </div>
        <p className="text-xs text-fg-muted">{panel.descriptor}</p>
      </CardHeader>
      <CardBody className="space-y-2">
        {panel.recent.length === 0 ? (
          <EmptyState
            icon={<span aria-hidden="true">∅</span>}
            title={emptyText.title}
            body={emptyText.body}
            primaryAction={emptyText.primary}
          />
        ) : (
          panel.recent.map(c => (
            <ComplaintCard key={c.complaint_id} complaint={c} locale={locale} />
          ))
        )}
      </CardBody>
    </Card>
  );
}
