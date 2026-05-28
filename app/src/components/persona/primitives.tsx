import type { ReactNode } from 'react';

import { ActionButton } from '@/components/persona/ActionButton';
import { AgentCard } from '@/components/persona/AgentCard';
import { Explanation } from '@/components/persona/Explanation';
import { Badge } from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import type { ActionDef, AgentBlock, FindingRow } from '@/types/persona-dashboards';

export function severityVariant(
  s: string,
): 'low' | 'medium' | 'high' | 'critical' | 'default' {
  switch (s.toLowerCase()) {
    case 'low':
    case 'baja':
      return 'low';
    case 'medium':
    case 'media':
      return 'medium';
    case 'high':
    case 'alta':
      return 'high';
    case 'critical':
    case 'critica':
      return 'critical';
    default:
      return 'default';
  }
}

export function ActionBar({ actions, locale }: { actions: ActionDef[]; locale: Locale }) {
  if (actions.length === 0) {
    return <p className="text-xs text-fg-muted">—</p>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {actions.map((a) => (
        <ActionButton key={a.action_id} action={a} locale={locale} />
      ))}
    </div>
  );
}

export function FindingsTable({
  rows,
  locale,
  max = 50,
}: {
  rows: FindingRow[];
  locale: Locale;
  max?: number;
}) {
  if (rows.length === 0) {
    return <p className="text-xs text-fg-muted">{bi(locale, 'Sin reclamos.', 'No complaints.')}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-border text-2xs uppercase tracking-wide text-fg-subtle">
            <th className="px-2 py-1.5 font-medium">{bi(locale, 'Reclamo', 'Complaint')}</th>
            <th className="px-2 py-1.5 font-medium">{bi(locale, 'Institución', 'Institution')}</th>
            <th className="px-2 py-1.5 font-medium">
              <span className="inline-flex items-center gap-1">
                {bi(locale, 'Severidad', 'Severity')}
                <Explanation explanationKey="severity_band" locale={locale} />
              </span>
            </th>
            <th className="px-2 py-1.5 font-medium">{bi(locale, 'Recibido', 'Received')}</th>
            <th className="px-2 py-1.5 font-medium">{bi(locale, 'Origen', 'Source')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, max).map((r) => (
            <tr key={r.complaint_id} className="border-b border-border-subtle">
              <td className="px-2 py-1.5 font-mono text-fg">{r.complaint_id}</td>
              <td className="px-2 py-1.5 text-fg">{r.institution_name}</td>
              <td className="px-2 py-1.5">
                <Badge variant={severityVariant(r.severity)}>{r.severity}</Badge>
              </td>
              <td className="px-2 py-1.5 font-mono text-fg-muted">
                {new Date(r.received_at).toLocaleString(locale, {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </td>
              <td className="px-2 py-1.5 font-mono text-2xs text-fg-subtle">{r.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Presentational building blocks shared across the five dashboards.
// Server-safe (no hooks); they embed the client AgentCard/Explanation
// where interactivity is needed.

export function Section({
  title,
  locale,
  explainKey,
  right,
  children,
}: {
  title: string;
  locale: Locale;
  explainKey?: string;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-sbs border border-border bg-surface shadow-sm">
      <header className="flex items-center justify-between gap-2 border-b border-border-subtle px-4 py-2.5">
        <h2 className="flex items-center gap-1.5 text-sm font-semibold tracking-tight text-fg">
          {title}
          {explainKey ? <Explanation explanationKey={explainKey} locale={locale} /> : null}
        </h2>
        {right ? <div className="shrink-0">{right}</div> : null}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}

export function KpiTile({
  label,
  value,
  locale,
  explainKey,
  contextData,
}: {
  label: string;
  value: string | number;
  locale: Locale;
  explainKey?: string;
  contextData?: Record<string, string | number>;
}) {
  return (
    <div className="rounded-sbs border border-border bg-surface-subtle px-3 py-2">
      <div className="flex items-center gap-1 text-2xs uppercase tracking-wide text-fg-subtle">
        {label}
        {explainKey ? (
          <Explanation explanationKey={explainKey} locale={locale} contextData={contextData} />
        ) : null}
      </div>
      <div className="mt-0.5 font-mono text-xl text-fg">{value}</div>
    </div>
  );
}

export function AgentGrid({
  agents,
  locale,
  opsView = false,
}: {
  agents: AgentBlock[];
  locale: Locale;
  opsView?: boolean;
}) {
  if (agents.length === 0) {
    return <p className="text-xs text-fg-muted">—</p>;
  }
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {agents.map((a) => (
        <AgentCard key={a.agent_id} agent={a} locale={locale} opsView={opsView} />
      ))}
    </div>
  );
}
