// SPDX-License-Identifier: Apache-2.0
// TaxonomyPanel — collapsed-by-default section on the findings detail
// page showing every (field, original → canonical) pair the taxonomy
// normalization step produced for this complaint.
//
// Reads from FindingDetailResponse.taxonomy_normalizations (extracted
// from the live-ingestion-orchestrator agent_run.final_output). When
// the list is empty the panel is hidden entirely — the page renders
// no whitespace gap.

'use client';

import { useState } from 'react';

import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import type { TaxonomyNormalization } from '@/types/findings';

interface TaxonomyPanelProps {
  normalizations: TaxonomyNormalization[];
  dictionaryVersion: string | null;
  labels: {
    title: string;
    show: string;
    hide: string;
    field: string;
    original: string;
    canonical: string;
    dictionary: string;
    empty: string;
  };
}

export function TaxonomyPanel({
  normalizations,
  dictionaryVersion,
  labels,
}: TaxonomyPanelProps) {
  const [open, setOpen] = useState(false);
  if (!normalizations || normalizations.length === 0) {
    return null;
  }
  return (
    <Card className="border-border">
      <CardHeader className="flex flex-row items-center justify-between border-b border-border px-4 py-3">
        <CardTitle>
          {labels.title}{' '}
          <span className="ml-1 font-mono text-2xs uppercase tracking-wider text-fg-muted">
            ({normalizations.length})
          </span>
        </CardTitle>
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          aria-expanded={open}
          className="rounded-sbs border border-border bg-surface-subtle px-2 py-1 font-mono text-2xs uppercase tracking-wider text-fg hover:border-brand-cyan"
        >
          {open ? labels.hide : labels.show}
        </button>
      </CardHeader>
      {open ? (
        <CardBody className="px-4 py-3">
          <table className="w-full table-fixed text-xs">
            <thead>
              <tr className="border-b border-border-subtle text-fg-muted">
                <th className="w-1/4 py-2 text-left font-mono text-2xs uppercase tracking-wider">
                  {labels.field}
                </th>
                <th className="w-1/3 py-2 text-left font-mono text-2xs uppercase tracking-wider">
                  {labels.original}
                </th>
                <th className="w-1/4 py-2 text-left font-mono text-2xs uppercase tracking-wider">
                  {labels.canonical}
                </th>
                <th className="w-1/6 py-2 text-right font-mono text-2xs uppercase tracking-wider">
                  {labels.dictionary}
                </th>
              </tr>
            </thead>
            <tbody>
              {normalizations.map((n, i) => (
                <tr
                  key={`${n.field_path}-${i}`}
                  className="border-b border-border-subtle last:border-0"
                >
                  <td className="py-2 font-mono tabular text-brand-navy">
                    {n.field_path}
                  </td>
                  <td className="py-2 font-mono text-fg-muted">
                    &quot;{n.original_value}&quot;
                  </td>
                  <td className="py-2 font-mono text-fg">{n.canonical_value}</td>
                  <td className="py-2 text-right font-mono text-2xs tabular text-fg-subtle">
                    {n.dictionary_version}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {dictionaryVersion ? (
            <p className="mt-2 font-mono text-2xs uppercase tracking-wider text-fg-subtle">
              {labels.dictionary}: {dictionaryVersion}
            </p>
          ) : null}
        </CardBody>
      ) : null}
    </Card>
  );
}
