// SPDX-License-Identifier: Apache-2.0
// Audit table — server-rendered but each row's <details> can expand
// to show the full diff + meta JSON (text-only per the drop ladder,
// no syntax highlighting).

import { Badge } from '@/components/ui';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui';
import type { AuditRow } from '@/types/audit';

interface AuditTableProps {
  rows: AuditRow[];
  locale: string;
  labels: {
    columns: {
      created_at: string;
      actor: string;
      action: string;
      object: string;
      details: string;
    };
    actor_type_user: string;
    actor_type_agent: string;
    details_label: string;
  };
}

export function AuditTable({ rows, locale, labels }: AuditTableProps) {
  const dtAbs = new Intl.DateTimeFormat(locale, {
    timeZone: 'America/Lima',
    year: '2-digit',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  const now = Date.now();

  function relative(iso: string): string {
    const ms = new Date(iso).getTime() - now;
    const s = Math.round(ms / 1000);
    if (Math.abs(s) < 60) return rtf.format(s, 'second');
    const m = Math.round(s / 60);
    if (Math.abs(m) < 60) return rtf.format(m, 'minute');
    const h = Math.round(m / 60);
    if (Math.abs(h) < 24) return rtf.format(h, 'hour');
    return rtf.format(Math.round(h / 24), 'day');
  }

  return (
    <Table>
      <TableHeader>
        <tr>
          <TableHead>{labels.columns.created_at}</TableHead>
          <TableHead>{labels.columns.actor}</TableHead>
          <TableHead>{labels.columns.action}</TableHead>
          <TableHead>{labels.columns.object}</TableHead>
          <TableHead>{labels.columns.details}</TableHead>
        </tr>
      </TableHeader>
      <TableBody>
        {rows.map(r => {
          const hasDetails =
            (r.diff && Object.keys(r.diff).length > 0) ||
            (r.meta && Object.keys(r.meta).length > 0);
          return (
            <TableRow key={r.id}>
              <TableCell className="text-2xs">
                <time dateTime={r.created_at} title={dtAbs.format(new Date(r.created_at))}>
                  <span className="tabular text-fg">{dtAbs.format(new Date(r.created_at))}</span>
                  <span className="ml-1 text-fg-muted">({relative(r.created_at)})</span>
                </time>
              </TableCell>
              <TableCell className="text-2xs">
                <Badge variant={r.actor_type === 'agent' ? 'source' : 'role'}>
                  {r.actor_type === 'agent' ? labels.actor_type_agent : labels.actor_type_user}
                </Badge>
                <span className="ml-1.5 font-mono text-fg">{r.actor_id}</span>
              </TableCell>
              <TableCell className="font-mono text-2xs text-fg">{r.action}</TableCell>
              <TableCell className="text-2xs">
                <span className="text-fg-muted">{r.object_type} ·</span>{' '}
                <span className="font-mono text-fg">{r.object_id}</span>
              </TableCell>
              <TableCell className="text-2xs">
                {hasDetails ? (
                  <details>
                    <summary className="cursor-pointer text-fg-link hover:underline">
                      {labels.details_label}
                    </summary>
                    {r.diff ? (
                      <pre className="mt-1 max-w-md overflow-x-auto rounded-sbs bg-surface-subtle p-2 text-2xs text-fg">
                        {JSON.stringify(r.diff, null, 2)}
                      </pre>
                    ) : null}
                    {r.meta ? (
                      <pre className="mt-1 max-w-md overflow-x-auto rounded-sbs bg-surface-subtle p-2 text-2xs text-fg">
                        {JSON.stringify(r.meta, null, 2)}
                      </pre>
                    ) : null}
                  </details>
                ) : (
                  <span className="text-fg-muted">—</span>
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
