'use client';

import { useState } from 'react';

import {
  Badge,
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import { AGENT_AVATARS } from '@/lib/persona';
import type { AgentBlock } from '@/types/persona-dashboards';

interface AgentCardProps {
  agent: AgentBlock;
  locale: Locale;
  /** SBS IT view: no character branding, technical agent_id only. */
  opsView?: boolean;
}

function statusVariant(status: string): 'low' | 'source' | 'medium' | 'default' {
  switch (status.toUpperCase()) {
    case 'RUNNING':
      return 'source'; // cyan/blue
    case 'DEGRADED':
      return 'medium'; // amber
    case 'IDLE':
    default:
      return 'default'; // grey
  }
}

function fmtPct(v: number | null): string {
  return v === null ? '—' : `${Math.round(v * 100)}%`;
}

function fmtMs(v: number | null): string {
  return v === null ? '—' : `${v} ms`;
}

function fmtTime(iso: string | null, locale: Locale): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString(locale, {
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function AgentCard({ agent, locale, opsView = false }: AgentCardProps) {
  const [open, setOpen] = useState(false);

  const showCharacter = agent.is_fi_facing && !opsView;
  const displayName = showCharacter
    ? bi(locale, agent.display_name_es ?? agent.agent_id, agent.display_name_en ?? agent.agent_id)
    : agent.agent_id;
  const tagline = showCharacter
    ? bi(locale, agent.tagline_es ?? '', agent.tagline_en ?? '')
    : '';
  const avatar = showCharacter ? AGENT_AVATARS[agent.agent_id] : undefined;
  const runs = agent.recent_runs ?? [];

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <button
          type="button"
          className="flex w-full flex-col gap-2 rounded-sbs border border-border bg-surface p-3 text-left transition-colors hover:border-brand-cyan hover:bg-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          <div className="flex items-center gap-2">
            {avatar ? (
              <span
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-2xs font-bold text-white"
                style={{ backgroundColor: '#002244' }}
                aria-hidden="true"
              >
                {avatar.initials}
              </span>
            ) : (
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-sbs border border-border bg-surface-subtle font-mono text-2xs text-fg-muted">
                {agent.agent_id.slice(0, 2).toUpperCase()}
              </span>
            )}
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-fg">
                {opsView ? <span className="font-mono">{displayName}</span> : displayName}
              </div>
              {tagline ? (
                <div className="truncate text-2xs text-fg-muted">{tagline}</div>
              ) : null}
            </div>
            <Badge variant={statusVariant(agent.status)}>{agent.status}</Badge>
          </div>

          <dl className="grid grid-cols-3 gap-1 text-2xs">
            <div>
              <dt className="text-fg-subtle">{bi(locale, 'Ejec.', 'Runs')}</dt>
              <dd className="font-mono text-fg">{agent.total_runs_in_window}</dd>
            </div>
            <div>
              <dt className="text-fg-subtle">{bi(locale, 'Éxito', 'Success')}</dt>
              <dd className="font-mono text-fg">{fmtPct(agent.success_rate)}</dd>
            </div>
            <div>
              <dt className="text-fg-subtle">{'p50'}</dt>
              <dd className="font-mono text-fg">{fmtMs(agent.p50_latency_ms)}</dd>
            </div>
          </dl>
        </button>
      </SheetTrigger>

      <SheetContent closeLabel={bi(locale, 'Cerrar', 'Close')}>
        <SheetTitle>
          {opsView ? <span className="font-mono">{displayName}</span> : displayName}
        </SheetTitle>
        <p className="mt-1 text-xs text-fg-muted">
          {`${bi(locale, 'Ventana', 'Window')}: 24h · ${bi(locale, 'Última', 'Last')} ${fmtTime(
            agent.last_run_at,
            locale,
          )} · p95 ${fmtMs(agent.p95_latency_ms)}`}
        </p>

        <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
          {bi(locale, 'Ejecuciones recientes', 'Recent runs')}
        </h3>
        {runs.length === 0 ? (
          <p className="mt-2 text-xs text-fg-muted">
            {bi(
              locale,
              'No hay detalle de ejecuciones para esta vista.',
              'No run detail available for this view.',
            )}
          </p>
        ) : (
          <ul className="mt-2 space-y-1.5 overflow-y-auto">
            {runs.map((run) => (
              <li
                key={run.audit_id}
                className="rounded-sbs border border-border bg-surface-subtle px-2.5 py-1.5 text-2xs"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-fg">{run.underlying_agent_id}</span>
                  <Badge variant={run.status === 'SUCCESS' ? 'low' : 'medium'}>
                    {run.status}
                  </Badge>
                </div>
                <div className="mt-0.5 flex items-center justify-between text-fg-muted">
                  <span>{fmtTime(run.started_at, locale)}</span>
                  <span className="font-mono">{`${run.duration_ms} ms`}</span>
                </div>
                {run.model_id ? (
                  <div className="mt-0.5 truncate font-mono text-fg-subtle">{run.model_id}</div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </SheetContent>
    </Sheet>
  );
}
