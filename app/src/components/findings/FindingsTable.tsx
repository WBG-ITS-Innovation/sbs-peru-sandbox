// SPDX-License-Identifier: Apache-2.0
// Findings table — used on the /app/findings list view. Row click
// navigates to /app/findings/:id; the row is wrapped in a <Link> so
// the URL changes without a JS navigation handler.

import Link from 'next/link';

import { Badge } from '@/components/ui';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui';
import { cn } from '@/lib/cn';
import type { FindingsListItem } from '@/types/findings';
import type { Severity } from '@/types/cockpit';

const SEVERITY_VARIANT: Record<Severity, 'low' | 'medium' | 'high' | 'critical'> = {
  low: 'low',
  medium: 'medium',
  high: 'high',
  critical: 'critical',
};

interface FindingsTableProps {
  items: FindingsListItem[];
  locale: string;
  labels: {
    columns: {
      complaint_id: string;
      institution: string;
      classification: string;
      confidence: string;
      severity: string;
      source: string;
      drafted_by_agent: string;
      received_at: string;
    };
    source: { tier1: string; tier2: string };
    drafted: string;
  };
}

export function FindingsTable({ items, locale, labels }: FindingsTableProps) {
  const dt = new Intl.DateTimeFormat(locale, {
    timeZone: 'America/Lima',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
  const nf = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return (
    <Table>
      <TableHeader>
        <tr>
          <TableHead>{labels.columns.complaint_id}</TableHead>
          <TableHead>{labels.columns.institution}</TableHead>
          <TableHead>{labels.columns.classification}</TableHead>
          <TableHead className="text-right">{labels.columns.confidence}</TableHead>
          <TableHead>{labels.columns.severity}</TableHead>
          <TableHead>{labels.columns.source}</TableHead>
          <TableHead>{labels.columns.received_at}</TableHead>
        </tr>
      </TableHeader>
      <TableBody>
        {items.map(item => {
          const href = `/findings/${encodeURIComponent(item.complaint_id)}`;
          return (
            <TableRow key={item.complaint_id} className="cursor-pointer">
              <TableCell className="font-mono text-2xs">
                <Link href={href} className="hover:underline">
                  {item.complaint_id}
                </Link>
              </TableCell>
              <TableCell>
                <Link href={href} className="block">
                  {item.institution_name}
                </Link>
              </TableCell>
              <TableCell>
                <Link href={href} className="flex items-center gap-1.5">
                  <span>{item.classification}</span>
                  {item.drafted_by_agent ? (
                    <Badge variant="source" className="px-1.5 py-0">
                      {labels.drafted}
                    </Badge>
                  ) : null}
                </Link>
              </TableCell>
              <TableCell className={cn('tabular text-right', !item.confidence && 'text-fg-muted')}>
                {item.confidence === null ? '—' : nf.format(item.confidence)}
              </TableCell>
              <TableCell>
                <Badge variant={SEVERITY_VARIANT[item.severity] ?? 'medium'}>
                  {item.severity}
                </Badge>
              </TableCell>
              <TableCell>
                <Badge variant="source">
                  {item.source === 'api_realtime' ? labels.source.tier1 : labels.source.tier2}
                </Badge>
              </TableCell>
              <TableCell className="tabular text-2xs text-fg-muted">
                <Link href={href}>
                  <time dateTime={item.received_at}>{dt.format(new Date(item.received_at))}</time>
                </Link>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
