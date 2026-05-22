// Approvals queue table — severity-sorted, oldest-first within band.

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
import type { ApprovalQueueItem } from '@/types/approvals';

const SEVERITY_VARIANT: Record<string, 'low' | 'medium' | 'high' | 'critical'> = {
  low: 'low',
  medium: 'medium',
  high: 'high',
  critical: 'critical',
};

interface ApprovalsTableProps {
  items: ApprovalQueueItem[];
  locale: string;
  labels: {
    complaint_id: string;
    institution: string;
    severity: string;
    time_pending: string;
    created_by: string;
  };
}

function fmtTimePending(seconds: number, locale: string): string {
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  if (seconds < 60) return rtf.format(-seconds, 'second');
  if (seconds < 3600) return rtf.format(-Math.round(seconds / 60), 'minute');
  if (seconds < 86400) return rtf.format(-Math.round(seconds / 3600), 'hour');
  return rtf.format(-Math.round(seconds / 86400), 'day');
}

export function ApprovalsTable({ items, locale, labels }: ApprovalsTableProps) {
  return (
    <Table>
      <TableHeader>
        <tr>
          <TableHead>{labels.complaint_id}</TableHead>
          <TableHead>{labels.institution}</TableHead>
          <TableHead>{labels.severity}</TableHead>
          <TableHead>{labels.time_pending}</TableHead>
          <TableHead>{labels.created_by}</TableHead>
        </tr>
      </TableHeader>
      <TableBody>
        {items.map(item => {
          const href = `/approvals/${item.id}`;
          return (
            <TableRow key={item.id} className="cursor-pointer">
              <TableCell className="font-mono text-2xs">
                <Link href={href} className="hover:underline">
                  {item.complaint_id}
                </Link>
              </TableCell>
              <TableCell>
                <Link href={href}>{item.institution_name}</Link>
              </TableCell>
              <TableCell>
                <Badge variant={SEVERITY_VARIANT[item.severity] ?? 'medium'}>
                  {item.severity}
                </Badge>
              </TableCell>
              <TableCell className="text-2xs text-fg-muted">
                <Link href={href}>{fmtTimePending(item.time_pending_seconds, locale)}</Link>
              </TableCell>
              <TableCell className="text-2xs text-fg-muted">
                <Link href={href}>{item.created_by}</Link>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
